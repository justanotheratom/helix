"""ORM → API-schema mapping helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import db, schemas
from .langfuse_link import traces_url as _traces_url
from .settings import settings


def job_to_schema(session: Session, job: db.Job) -> schemas.Job:
    pv = session.get(db.ProgramVersion, job.program_version_id)
    ds = session.get(db.Dataset, job.dataset_id)
    sp = session.get(db.Split, job.split_id)
    program_name = None
    if pv is not None:
        prog = session.get(db.Program, pv.program_id)
        program_name = prog.name if prog else None

    ui_url = f"{settings.public_base_url}/jobs/{job.id}"
    traces_url = _traces_url(job.id)

    return schemas.Job(
        id=job.id,
        type=job.type,  # type: ignore[arg-type]
        status=job.status,  # type: ignore[arg-type]
        repo_id=job.repo_id,
        user_id=job.user_id,
        snapshot_id=job.snapshot_id,
        blocked_reason=job.blocked_reason,
        program=program_name,
        version=pv.version if pv else None,
        dataset=ds.version if ds else None,
        split=sp.version if sp else None,
        parent_job_id=job.parent_job_id,
        config_path=job.config_path,
        baked_sha=job.baked_sha,
        run_label=job.run_label,
        attempt=job.attempt,
        worker_id=job.worker_id,
        lease_expires_at=job.lease_expires_at,
        emitted_run_number=job.emitted_run_number,
        export_run_number=job.export_run_number,
        created_at=job.created_at,
        started_at=job.started_at,
        ended_at=job.ended_at,
        exit_code=job.exit_code,
        summary=job.summary,
        ui_url=ui_url,
        traces_url=traces_url,
    )


def artifact_to_schema(a: db.Artifact) -> schemas.Artifact:
    return schemas.Artifact(
        id=a.id,
        job_id=a.job_id,
        relative_path=a.relative_path,
        kind=a.kind,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        mime=a.mime,
        attempt=a.attempt,
        created_at=a.created_at,
    )
