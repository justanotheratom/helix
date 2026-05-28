"""Helix-native trace endpoints — proxy Langfuse's REST API on the internal
network so the browser never hits Langfuse directly. This is what lets us run
Helix on a single host port (Langfuse loses its :3010 binding)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from .. import db, langfuse_client


router = APIRouter(tags=["traces"])


@router.get("/jobs/{job_id}/traces")
async def list_job_traces(
    job_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
):
    """List traces belonging to this job (filtered by Langfuse `environment`
    == the job's run_label)."""
    with db.get_session() as session:
        job = session.get(db.Job, job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        run_label = job.run_label
    try:
        return await langfuse_client.list_traces(
            environment=run_label, limit=limit, page=page
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"langfuse: {e}")


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Full trace + nested observations for one Langfuse trace id."""
    try:
        return await langfuse_client.get_trace(trace_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"langfuse: {e}")
