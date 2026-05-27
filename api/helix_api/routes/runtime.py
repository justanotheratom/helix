from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import select

from .. import db, schemas
from ..settings import settings

router = APIRouter(tags=["runtime"])


@router.get("/runtime/baked-sha", response_model=schemas.BakedShaInfo)
def get_baked_sha() -> schemas.BakedShaInfo:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)
    with db.get_session() as session:
        rows = session.execute(
            select(db.WorkerHeartbeat).where(db.WorkerHeartbeat.last_seen >= cutoff)
        ).scalars().all()
    return schemas.BakedShaInfo(
        baked_sha=settings.baked_repo_sha,
        workers=[
            schemas.WorkerHeartbeatInfo(
                worker_id=w.worker_id, baked_sha=w.baked_sha, last_seen=w.last_seen
            )
            for w in rows
        ],
    )
