"""Job CRUD: submit (compile/eval), list, get, cancel, traces deep-link.

Multipart submissions carry a JSON `metadata` part + a `bundle` tar.gz.
We parse metadata into Pydantic models and stash the bundle in blob
storage keyed by job_id (one bundle per multi-config submission; each
job row points to the same bundle_blob_key).
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, select

from .. import blob, db, dispatch, redis_bus, schemas
from ..langfuse_link import traces_url
from ..serialize import job_to_schema
from ..settings import settings

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _store_bundle(key_prefix: str, bundle: UploadFile | None) -> str | None:
    if bundle is None:
        return None
    data = bundle.file.read()
    if not data:
        return None
    key = f"bundles/{key_prefix}/{uuid.uuid4().hex}.tar.gz"
    blob.put_bytes(key, data, content_type="application/gzip")
    return key


# ----- Compile -----------------------------------------------------------------

@router.post("/compile", response_model=List[schemas.JobSubmissionResult], status_code=201)
async def submit_compile(
    metadata: str = Form(..., description="JSON CompileSubmissionMetadata"),
    bundle: UploadFile | None = File(default=None),
) -> List[schemas.JobSubmissionResult]:
    meta = schemas.CompileSubmissionMetadata.model_validate_json(metadata)
    bundle_key = _store_bundle(meta.snapshot_digest or meta.baked_sha or meta.repo_id, bundle)

    snap_cfg = _cfg_for_snapshot(meta.snapshot_id)
    out: list[schemas.JobSubmissionResult] = []
    with db.get_session() as session:
        for cfg in meta.configs:
            program = meta.program or _infer_program(cfg.config_path, snap_cfg)
            version = meta.version or _infer_version(cfg.config_path, snap_cfg)
            if not (program and version):
                raise HTTPException(400, f"Could not infer program/version from {cfg.config_path}")

            job = dispatch.insert_queued_job(
                session,
                repo_id=meta.repo_id,
                type_="compile",
                program=program,
                version=version,
                dataset=cfg.dataset,
                split=cfg.split,
                config_path=cfg.config_path,
                bundle_blob_key=bundle_key,
                baked_sha=meta.baked_sha,
                snapshot_id=meta.snapshot_id,
                helix_runtime_version=meta.helix_runtime_version,
                parent_job_id=None,
            )
            session.flush()  # need job.id

            # If auto_eval requested, queue an eval row pointing at this compile
            # in status='queued' but with a sentinel — workers ignore it until
            # the parent succeeds. (Auto-eval is fired by the worker on success.)
            # In v1 we record auto_eval_config_path on the parent's summary so
            # the worker knows to spawn it.
            if cfg.auto_eval_config_path:
                job.summary = {"auto_eval_config_path": cfg.auto_eval_config_path}

            out.append(
                schemas.JobSubmissionResult(
                    job_id=job.id,
                    run_label=job.run_label,
                    ui_url=f"{settings.public_base_url}/jobs/{job.id}",
                    traces_url=traces_url(job.id),
                )
            )
        session.commit()
    return out


# ----- Eval --------------------------------------------------------------------

@router.post("/eval", response_model=List[schemas.JobSubmissionResult], status_code=201)
async def submit_eval(
    metadata: str = Form(...),
    bundle: UploadFile | None = File(default=None),
) -> List[schemas.JobSubmissionResult]:
    meta = schemas.EvalSubmissionMetadata.model_validate_json(metadata)
    bundle_key = _store_bundle(meta.snapshot_digest or meta.baked_sha or meta.repo_id, bundle)
    if bundle_key is None and meta.inherit_bundle_from_compile_job_id is not None:
        with db.get_session() as inh_session:
            parent = inh_session.get(db.Job, meta.inherit_bundle_from_compile_job_id)
            if parent is not None and parent.bundle_blob_key:
                bundle_key = parent.bundle_blob_key

    out: list[schemas.JobSubmissionResult] = []
    with db.get_session() as session:
        for cfg in meta.configs:
            parent = session.get(db.Job, cfg.compile_job_id)
            if parent is None or parent.type != "compile":
                raise HTTPException(404, f"compile job {cfg.compile_job_id} not found")
            if parent.status != "succeeded":
                raise HTTPException(
                    409,
                    f"compile job {cfg.compile_job_id} is in status "
                    f"{parent.status!r}; only 'succeeded' compiles can be evaluated",
                )

            # Inherit program/version/dataset/split from parent unless overridden.
            ppv = session.get(db.ProgramVersion, parent.program_version_id)
            pds = session.get(db.Dataset, parent.dataset_id)
            psp = session.get(db.Split, parent.split_id)
            program_obj = session.get(db.Program, ppv.program_id)
            assert ppv and pds and psp and program_obj

            # Inherit repo_id/snapshot/runtime from the parent compile (the eval
            # must run against the same source) unless the submission overrides.
            job = dispatch.insert_queued_job(
                session,
                repo_id=parent.repo_id,
                type_="eval",
                program=program_obj.name,
                version=ppv.version,
                dataset=cfg.dataset or pds.version,
                split=cfg.split or psp.version,
                config_path=cfg.config_path,
                bundle_blob_key=bundle_key,
                baked_sha=meta.baked_sha or parent.baked_sha,
                snapshot_id=meta.snapshot_id or parent.snapshot_id,
                helix_runtime_version=meta.helix_runtime_version or parent.helix_runtime_version,
                parent_job_id=parent.id,
            )
            session.flush()
            out.append(
                schemas.JobSubmissionResult(
                    job_id=job.id,
                    run_label=job.run_label,
                    ui_url=f"{settings.public_base_url}/jobs/{job.id}",
                    traces_url=traces_url(job.id),
                )
            )
        session.commit()
    return out


# ----- List / get / cancel ----------------------------------------------------

@router.get("", response_model=List[schemas.Job])
def list_jobs(
    program: str | None = Query(default=None),
    version: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    split: str | None = Query(default=None),
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[schemas.Job]:
    with db.get_session() as session:
        q = select(db.Job)
        if status:
            q = q.where(db.Job.status == status)
        if type:
            q = q.where(db.Job.type == type)
        if program:
            q = q.join(db.ProgramVersion, db.ProgramVersion.id == db.Job.program_version_id)
            q = q.join(db.Program, db.Program.id == db.ProgramVersion.program_id)
            q = q.where(db.Program.name == program)
            if version:
                q = q.where(db.ProgramVersion.version == version)
        elif version:
            q = q.join(db.ProgramVersion, db.ProgramVersion.id == db.Job.program_version_id)
            q = q.where(db.ProgramVersion.version == version)
        if dataset:
            q = q.join(db.Dataset, db.Dataset.id == db.Job.dataset_id)
            q = q.where(db.Dataset.version == dataset)
        if split:
            q = q.join(db.Split, db.Split.id == db.Job.split_id)
            q = q.where(db.Split.version == split)
        q = q.order_by(desc(db.Job.created_at)).limit(limit)
        rows = session.execute(q).scalars().all()
        return [job_to_schema(session, j) for j in rows]


@router.get("/{job_id}", response_model=schemas.Job)
def get_job(job_id: uuid.UUID) -> schemas.Job:
    with db.get_session() as session:
        job = session.get(db.Job, job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job_to_schema(session, job)


@router.post("/{job_id}/cancel", response_model=schemas.Job, status_code=202)
def cancel_job(job_id: uuid.UUID) -> schemas.Job:
    with db.get_session() as session:
        job = session.get(db.Job, job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        if job.status not in ("queued", "running"):
            raise HTTPException(409, f"cannot cancel a job in status {job.status}")
        if job.status == "queued":
            # No worker yet → mark cancelled directly.
            from datetime import datetime, timezone
            job.status = "cancelled"
            job.ended_at = datetime.now(timezone.utc)
            job.cancel_requested = True
        else:
            # Running: persist the cancel intent durably BEFORE publishing
            # the transient redis signal. If the worker has crashed, the
            # recovery sweep will see cancel_requested=true and finalize
            # the job as 'cancelled' instead of requeueing it.
            job.cancel_requested = True
        session.commit()
        # Publish the live signal — workers subscribe per-job and will
        # SIGTERM+SIGKILL the subprocess pgrp.
        redis_bus.publish_cancel(str(job_id))
        return job_to_schema(session, job)


# /{job_id}/traces is served by routes/traces.py (lists Langfuse traces for
# this job via the internal proxy); the legacy deep-link endpoint is gone now
# that Langfuse isn't externally reachable.


# ----- helpers ----------------------------------------------------------------

@lru_cache(maxsize=128)
def _cfg_for_snapshot(snapshot_id: uuid.UUID | None):
    """HelixConfig parsed from a snapshot's embedded config_blob.

    This is how a generic, multi-tenant API infers program/version without
    baking any consumer .helix.toml: each submission carries a snapshot_id
    whose manifest holds the authoritative config. Falls back to the
    process-global config (Phase-1 / single-tenant) when no snapshot is given.
    """
    if snapshot_id is None:
        from ..settings import helix_config
        return helix_config()
    with db.get_session() as session:
        snap = session.get(db.Snapshot, snapshot_id)
        if snap is None or not snap.config_blob:
            return None
    try:
        import tomllib

        from helix_config import parse_config
        return parse_config(tomllib.loads(snap.config_blob))
    except Exception:
        return None


def _infer_pv(config_path: str, cfg=None) -> tuple[str | None, str | None]:
    """(program, version) from <overlay_root>/<p>/<v>/..., config-driven."""
    if cfg is None:
        from ..settings import helix_config
        cfg = helix_config()
    if cfg is None:
        return None, None
    m = cfg.program_version_re().search(config_path)
    return (m.group(1), m.group(2)) if m else (None, None)


def _infer_program(config_path: str, cfg=None) -> str | None:
    return _infer_pv(config_path, cfg)[0]


def _infer_version(config_path: str, cfg=None) -> str | None:
    return _infer_pv(config_path, cfg)[1]
