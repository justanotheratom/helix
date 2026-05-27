"""Snapshot manifest + content-addressed tarball store.

A snapshot is the consumer's base-dir tree at a commit, scoped + digested by
the CLI. The object key is digest-primary (snapshots/<digest>.tar.gz) so
identical trees dedupe; many manifest rows may point at one digest.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from .. import blob, db

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


class SnapshotMeta(BaseModel):
    repo_id: str
    digest: str
    git_sha: str | None = None
    helix_runtime_version: str
    lockfile_digest: str | None = None
    base_fingerprint: str | None = None
    config_blob: str
    seed_state: dict = {}
    oob_blobs: dict = {}


class SnapshotRef(BaseModel):
    snapshot_id: uuid.UUID
    digest: str
    existed: bool


class OobRef(BaseModel):
    digest: str
    existed: bool


def _object_key(digest: str) -> str:
    return f"snapshots/{digest}.tar.gz"


def _oob_key(digest: str) -> str:
    return f"oob/{digest}.tar.gz"


@router.post("/oob", response_model=OobRef, status_code=201)
async def publish_oob(
    digest: str = Form(...),
    tarball: UploadFile | None = File(default=None),
) -> OobRef:
    """Store an out-of-band data blob digest-primary (idempotent).

    The CLI uploads each [snapshot].out_of_band root as its own
    content-addressed blob, then records {root: digest} in the snapshot
    manifest. Identical data dedupes across snapshots/repos.
    """
    key = _oob_key(digest)
    if blob.stat(key) is not None:
        return OobRef(digest=digest, existed=True)
    if tarball is None:
        raise HTTPException(400, "tarball required for a new oob digest")
    data = tarball.file.read()
    blob.put_bytes(key, data, content_type="application/gzip")
    return OobRef(digest=digest, existed=False)


@router.get("/resolve")
def resolve(repo_id: str, digest: str) -> SnapshotRef:
    """Return an existing snapshot for (repo_id, digest), or 404."""
    with db.get_session() as session:
        row = session.execute(
            select(db.Snapshot).where(
                db.Snapshot.repo_id == repo_id, db.Snapshot.digest == digest
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "snapshot not found")
        return SnapshotRef(snapshot_id=row.id, digest=row.digest, existed=True)


@router.post("", response_model=SnapshotRef, status_code=201)
async def publish(
    metadata: str = Form(...),
    tarball: UploadFile | None = File(default=None),
) -> SnapshotRef:
    """Create (or return existing) a snapshot manifest row + store its tarball.

    Idempotent on (repo_id, digest): a second publish of the same digest
    returns the existing row and skips the upload.
    """
    meta = SnapshotMeta.model_validate_json(metadata)

    with db.get_session() as session:
        existing = session.execute(
            select(db.Snapshot).where(
                db.Snapshot.repo_id == meta.repo_id, db.Snapshot.digest == meta.digest
            )
        ).scalar_one_or_none()
        if existing is not None:
            return SnapshotRef(snapshot_id=existing.id, digest=existing.digest, existed=True)

        # Upload the tarball digest-primary (skip if the object already exists,
        # e.g. another repo published the identical tree).
        key = _object_key(meta.digest)
        if blob.stat(key) is None:
            if tarball is None:
                raise HTTPException(400, "tarball required for a new digest")
            data = tarball.file.read()
            blob.put_bytes(key, data, content_type="application/gzip")

        row = db.Snapshot(
            id=uuid.uuid4(),
            repo_id=meta.repo_id,
            digest=meta.digest,
            git_sha=meta.git_sha,
            created_at=datetime.now(timezone.utc),
            helix_runtime_version=meta.helix_runtime_version,
            lockfile_digest=meta.lockfile_digest,
            base_fingerprint=meta.base_fingerprint,
            config_blob=meta.config_blob,
            seed_state=meta.seed_state,
            oob_blobs=meta.oob_blobs,
        )
        session.add(row)
        session.commit()
        return SnapshotRef(snapshot_id=row.id, digest=row.digest, existed=False)
