"""POST /api/jobs/import-compile — idempotent import of a legacy results dir."""
from __future__ import annotations

import hashlib
import io
import tarfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import select

from .. import blob, db, dispatch, schemas
from ..identity import submission_user_id
from ..langfuse_link import traces_url
from ..settings import settings

router = APIRouter(tags=["jobs"])


@router.post("/jobs/import-compile", response_model=schemas.JobSubmissionResult)
async def import_compile(
    metadata: str = Form(...),
    bundle: UploadFile = File(...),
    cf_access_client_id: str | None = Header(default=None, alias="CF-Access-Client-Id"),
):
    meta = schemas.ImportCompileMetadata.model_validate_json(metadata)
    user_id = submission_user_id(meta.user_id, cf_access_client_id)
    tar_bytes = bundle.file.read()

    with db.get_session() as session:
        pv_id, _, _ = dispatch.upsert_lookup_chain(
            session, meta.repo_id, meta.program, meta.version, meta.dataset, meta.split
        )

        # Idempotency: re-look-up by (program_version_id, emitted_run_number).
        existing = session.execute(
            select(db.Job).where(
                db.Job.type == "compile",
                db.Job.program_version_id == pv_id,
                db.Job.emitted_run_number == meta.emitted_run_number,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return schemas.JobSubmissionResult(
                job_id=existing.id,
                run_label=existing.run_label,
                ui_url=f"{settings.public_base_url}/jobs/{existing.id}",
                traces_url=traces_url(existing.id),
            )

        job = dispatch.insert_queued_job(
            session,
            repo_id=meta.repo_id,
            user_id=user_id,
            type_="compile",
            program=meta.program,
            version=meta.version,
            dataset=meta.dataset,
            split=meta.split,
            config_path=meta.compile_config_path or "",
            bundle_blob_key=None,
            baked_sha=None,
            parent_job_id=None,
            status="succeeded",
            emitted_run_number=meta.emitted_run_number,
        )
        job.started_at = datetime.now(timezone.utc)
        job.ended_at = datetime.now(timezone.utc)
        session.flush()

        # Extract bundle, upload each member as an artifact (skip evals/** and helix/**).
        # The member name becomes artifacts.relative_path which `helix export`
        # uses to write back to disk — validate strictly to keep an attacker
        # from crafting a tar that escapes the export target later.
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # Validate the ORIGINAL name first — lstrip("./") would
                # strip a leading "../" to "escape.txt" and let traversal slip
                # through. Only after validation do we normalize for storage.
                raw = member.name
                if raw.startswith("/") or "\x00" in raw:
                    raise HTTPException(400, f"bundle member has absolute or null path: {raw!r}")
                parts = raw.replace("\\", "/").split("/")
                if any(p == ".." for p in parts):
                    raise HTTPException(400, f"bundle member has '..' segment: {raw!r}")
                rel = raw.lstrip("./")
                if rel.startswith("evals/") or rel.startswith("helix/"):
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                data = f.read()
                sha = hashlib.sha256(data).hexdigest()
                blob_key = f"artifacts/{job.id}/0/{rel}"
                blob.put_bytes(blob_key, data)
                kind = _classify(rel)
                session.add(
                    db.Artifact(
                        job_id=job.id,
                        relative_path=rel,
                        kind=kind,
                        blob_key=blob_key,
                        size_bytes=len(data),
                        sha256=sha,
                        mime=None,
                        attempt=0,
                        created_at=datetime.now(timezone.utc),
                    )
                )

        session.commit()

        # Seed legacy_compile_run_numbers so future compiles of this
        # program_version pick numbers > emitted_run_number.
        from sqlalchemy import text
        session.execute(
            text(
                """
                INSERT INTO legacy_compile_run_numbers (program_version_id, next_number)
                VALUES (:pv, :n)
                ON CONFLICT (program_version_id)
                DO UPDATE SET next_number = GREATEST(legacy_compile_run_numbers.next_number, :n)
                """
            ),
            {"pv": pv_id, "n": meta.emitted_run_number + 1},
        )
        session.commit()

        return schemas.JobSubmissionResult(
            job_id=job.id,
            run_label=job.run_label,
            ui_url=f"{settings.public_base_url}/jobs/{job.id}",
            traces_url=traces_url(job.id),
        )


def _classify(rel: str) -> str:
    if rel == "program.hash":
        return "program_hash"
    if rel.endswith(".yaml") and "/" not in rel:
        return "config"
    # compiled_program/ = the trained program (eval artifact); deploy/ = the
    # post_compile=transplant serving artifact. The compile/ nested form is
    # read-only back-compat for historical run dirs.
    if (
        rel.startswith("compiled_program/program.pkl")
        or rel.startswith("deploy/compiled_program/program.pkl")
        or rel.startswith("compile/compiled_program/program.pkl")
    ):
        return "compiled_program"
    if rel.startswith("gepa_logs/"):
        return "gepa_log"
    if rel.startswith("compile/program.py"):
        return "program_py"
    return "other"
