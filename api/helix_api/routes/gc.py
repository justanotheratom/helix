"""Storage GC keyed on Postgres refcounts.

A snapshot blob (snapshots/<digest>.tar.gz) is reachable while any snapshot
manifest row points at that digest AND any job references that manifest. We
delete manifest rows that no job references and that are older than a grace
window; a blob is removed only once NO surviving manifest row shares its
digest (digests are shared across repos/commits). Orphan overlay bundles
(no job.bundle_blob_key) older than the grace window are swept too.

GC is destructive, so dry_run is honored end-to-end; the CLI defaults to a
dry run and requires --apply to delete.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from .. import blob, db

router = APIRouter(prefix="/gc", tags=["gc"])


class GcReport(BaseModel):
    dry_run: bool
    grace_hours: int
    deleted_manifests: int
    deleted_snapshot_blobs: int
    deleted_orphan_bundles: int
    snapshot_blob_keys: list[str]
    bundle_keys: list[str]


def _oob_keys_for(digest: str, session) -> list[str]:
    """Out-of-band data blobs referenced by a snapshot's manifest, if any."""
    snap = session.execute(
        select(db.Snapshot).where(db.Snapshot.digest == digest)
    ).scalars().first()
    keys: list[str] = []
    oob = getattr(snap, "oob_blobs", None) if snap else None
    if isinstance(oob, dict):
        keys = [f"oob/{d}.tar.gz" for d in oob.values()]
    return keys


@router.post("", response_model=GcReport)
def garbage_collect(
    grace_hours: int = Query(default=24, ge=0),
    dry_run: bool = Query(default=True),
) -> GcReport:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_hours)

    snapshot_blob_keys: list[str] = []
    bundle_keys: list[str] = []
    deleted_manifests = 0

    with db.get_session() as session:
        referenced_snap_ids = {
            row[0]
            for row in session.execute(
                select(db.Job.snapshot_id).where(db.Job.snapshot_id.isnot(None)).distinct()
            )
        }
        all_snaps = session.execute(select(db.Snapshot)).scalars().all()

        # Manifest rows safe to drop: unreferenced + past the grace window.
        def _created(s):
            c = s.created_at
            return c if c.tzinfo else c.replace(tzinfo=timezone.utc)

        to_delete = [
            s for s in all_snaps
            if s.id not in referenced_snap_ids and _created(s) < cutoff
        ]
        del_ids = {s.id for s in to_delete}

        # A digest's blob is removable only if no SURVIVING manifest shares it.
        survivor_digests = {s.digest for s in all_snaps if s.id not in del_ids}
        removable_digests = {s.digest for s in to_delete if s.digest not in survivor_digests}
        for d in removable_digests:
            snapshot_blob_keys.append(f"snapshots/{d}.tar.gz")
            snapshot_blob_keys.extend(_oob_keys_for(d, session))

        if not dry_run:
            for s in to_delete:
                session.delete(s)
            session.commit()
        deleted_manifests = len(to_delete)

        referenced_bundles = {
            row[0]
            for row in session.execute(
                select(db.Job.bundle_blob_key).where(db.Job.bundle_blob_key.isnot(None)).distinct()
            )
        }

    # Orphan overlay bundles (no job references them) older than the window.
    for obj in blob.list_objects("bundles/"):
        name = obj.object_name
        lm = obj.last_modified
        if lm is not None and lm.tzinfo is None:
            lm = lm.replace(tzinfo=timezone.utc)
        if name not in referenced_bundles and (lm is None or lm < cutoff):
            bundle_keys.append(name)

    if not dry_run:
        for key in snapshot_blob_keys + bundle_keys:
            try:
                blob.remove_object(key)
            except Exception:  # noqa: BLE001 — best-effort; manifest already gone
                pass

    return GcReport(
        dry_run=dry_run,
        grace_hours=grace_hours,
        deleted_manifests=deleted_manifests,
        deleted_snapshot_blobs=len(snapshot_blob_keys),
        deleted_orphan_bundles=len(bundle_keys),
        snapshot_blob_keys=snapshot_blob_keys,
        bundle_keys=bundle_keys,
    )
