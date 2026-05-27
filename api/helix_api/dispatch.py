"""Job-row creation: resolve program/version/dataset/split FKs and INSERT queued jobs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db
from .run_label import make_run_label


def upsert_lookup_chain(
    session: Session, repo_id: str, program: str, version: str, dataset: str, split: str
) -> tuple[int, int, int]:
    """Return (program_version_id, dataset_id, split_id), creating rows as needed.

    Program lookup is scoped by repo_id so two repos can share a program name.
    """
    prog = session.execute(
        select(db.Program).where(db.Program.repo_id == repo_id, db.Program.name == program)
    ).scalar_one_or_none()
    if prog is None:
        prog = db.Program(repo_id=repo_id, name=program)
        session.add(prog)
        session.flush()

    pv = session.execute(
        select(db.ProgramVersion).where(
            db.ProgramVersion.program_id == prog.id, db.ProgramVersion.version == version
        )
    ).scalar_one_or_none()
    if pv is None:
        pv = db.ProgramVersion(program_id=prog.id, version=version)
        session.add(pv)
        session.flush()

    ds = session.execute(
        select(db.Dataset).where(
            db.Dataset.program_version_id == pv.id, db.Dataset.version == dataset
        )
    ).scalar_one_or_none()
    if ds is None:
        ds = db.Dataset(program_version_id=pv.id, version=dataset)
        session.add(ds)
        session.flush()

    sp = session.execute(
        select(db.Split).where(db.Split.dataset_id == ds.id, db.Split.version == split)
    ).scalar_one_or_none()
    if sp is None:
        sp = db.Split(dataset_id=ds.id, version=split)
        session.add(sp)
        session.flush()

    return pv.id, ds.id, sp.id


def insert_queued_job(
    session: Session,
    *,
    repo_id: str,
    type_: str,
    program: str,
    version: str,
    dataset: str,
    split: str,
    config_path: str,
    bundle_blob_key: str | None,
    baked_sha: str | None = None,
    snapshot_id: uuid.UUID | None = None,
    helix_runtime_version: str | None = None,
    parent_job_id: uuid.UUID | None,
    status: str = "queued",
    emitted_run_number: int | None = None,
) -> db.Job:
    pv_id, ds_id, sp_id = upsert_lookup_chain(session, repo_id, program, version, dataset, split)

    job_id = uuid.uuid4()
    # run_label includes repo_id so Langfuse environments don't collide across repos.
    label_stem = f"{repo_id}_{type_}_{program}_{version}_{config_path.rsplit('/', 1)[-1].rsplit('.', 1)[0]}_{job_id.hex[:8]}"
    run_label = make_run_label(label_stem)

    job = db.Job(
        id=job_id,
        type=type_,
        status=status,
        repo_id=repo_id,
        program_version_id=pv_id,
        dataset_id=ds_id,
        split_id=sp_id,
        parent_job_id=parent_job_id,
        config_path=config_path,
        bundle_blob_key=bundle_blob_key,
        baked_sha=baked_sha,
        snapshot_id=snapshot_id,
        helix_runtime_version=helix_runtime_version,
        run_label=run_label,
        attempt=0,
        emitted_run_number=emitted_run_number,
        created_at=datetime.now(timezone.utc),
    )
    session.add(job)
    return job
