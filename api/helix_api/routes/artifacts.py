"""Artifact list + per-id stream + bulk tar.gz."""
from __future__ import annotations

import io
import tarfile
import uuid
from typing import Iterator, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from .. import blob, db, schemas
from ..serialize import artifact_to_schema

router = APIRouter(prefix="/jobs/{job_id}", tags=["artifacts"])


def _current_attempt(session, job_id: uuid.UUID) -> int | None:
    """The attempt corresponding to the row's terminal/current state.

    Used to filter artifact reads so partial uploads from a crashed
    earlier attempt don't surface alongside the winning attempt.
    """
    job = session.get(db.Job, job_id)
    return job.attempt if job else None


@router.get("/artifacts", response_model=List[schemas.Artifact])
def list_artifacts(
    job_id: uuid.UUID,
    kind: str | None = Query(default=None),
    prefix: str | None = Query(default=None),
) -> list[schemas.Artifact]:
    with db.get_session() as session:
        cur_att = _current_attempt(session, job_id)
        if cur_att is None:
            raise HTTPException(404, "job not found")
        q = select(db.Artifact).where(
            db.Artifact.job_id == job_id,
            db.Artifact.attempt == cur_att,
        )
        if kind:
            q = q.where(db.Artifact.kind == kind)
        if prefix:
            q = q.where(db.Artifact.relative_path.like(f"{prefix}%"))
        rows = session.execute(q.order_by(db.Artifact.relative_path)).scalars().all()
        return [artifact_to_schema(a) for a in rows]


@router.get("/artifacts/{artifact_id}")
def get_artifact(job_id: uuid.UUID, artifact_id: uuid.UUID):
    with db.get_session() as session:
        art = session.get(db.Artifact, artifact_id)
        if art is None or art.job_id != job_id:
            raise HTTPException(404, "artifact not found")
        obj = blob.get_object_stream(art.blob_key)
        return StreamingResponse(
            _iter_object(obj),
            media_type=art.mime or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{art.relative_path.split("/")[-1]}"',
                "Content-Length": str(art.size_bytes),
            },
        )


def _iter_object(obj) -> Iterator[bytes]:
    try:
        for chunk in obj.stream(amt=64 * 1024):
            yield chunk
    finally:
        obj.close()
        obj.release_conn()


@router.get("/artifacts.tar.gz")
def download_artifacts_tar(job_id: uuid.UUID, prefix: str | None = Query(default=None)):
    """Stream a tar.gz containing every artifact at its relative_path."""
    with db.get_session() as session:
        cur_att = _current_attempt(session, job_id)
        if cur_att is None:
            raise HTTPException(404, "job not found")
        q = select(db.Artifact).where(
            db.Artifact.job_id == job_id,
            db.Artifact.attempt == cur_att,
        )
        if prefix:
            q = q.where(db.Artifact.relative_path.like(f"{prefix}%"))
        rows = session.execute(q.order_by(db.Artifact.relative_path)).scalars().all()

    if not rows:
        raise HTTPException(404, "no artifacts")

    def producer() -> Iterator[bytes]:
        buf = _StreamingBuf()
        with tarfile.open(fileobj=buf, mode="w|gz") as tar:
            for art in rows:
                data = b"".join(_iter_object(blob.get_object_stream(art.blob_key)))
                info = tarfile.TarInfo(name=art.relative_path)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
                yield from buf.drain()
            tar.close()
        yield from buf.drain()

    return StreamingResponse(
        producer(),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{job_id}.tar.gz"'},
    )


class _StreamingBuf:
    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self._chunks.append(data)
        return len(data)

    def drain(self) -> Iterator[bytes]:
        chunks, self._chunks = self._chunks, []
        for c in chunks:
            yield c

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass
