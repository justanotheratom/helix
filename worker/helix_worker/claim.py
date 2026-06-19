"""Claim and recovery logic — Postgres queue with FOR UPDATE SKIP LOCKED."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import settings
from .db import engine


def claim_next_job() -> dict[str, Any] | None:
    """Claim the oldest queued job for a user with no running job.

    No baked_sha fence anymore: any worker can claim any repo's job. After
    claiming, the worker materializes the job's snapshot and checks runtime
    compatibility (runner._prepare); a job it can't satisfy is parked
    `blocked` (not failed, not requeued) so it never hot-loops.

    `blocked` rows are excluded by `status='queued'`. A queued job must have
    a snapshot_id to run in snapshot mode — those without are swept by
    fail_stale_queued_jobs.

    The matching migration adds a partial unique index on (user_id) for
    running jobs. That index is the race-proof guard when multiple workers try
    to claim queued jobs for the same user at the same time.
    """
    sql = text(
        """
        UPDATE jobs
        SET status='running',
            worker_id=:wid,
            started_at=COALESCE(started_at, now()),
            lease_expires_at=now() + CAST(:lease || ' seconds' AS interval),
            attempt=attempt + 1
        WHERE id = (
          SELECT q.id FROM jobs q
          WHERE q.status='queued'
            AND q.cancel_requested = false
            AND q.snapshot_id IS NOT NULL
            AND NOT EXISTS (
              SELECT 1 FROM jobs r
              WHERE r.status='running'
                AND r.user_id = q.user_id
            )
          ORDER BY q.created_at
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        RETURNING id, type, status, repo_id, program_version_id, dataset_id, split_id,
                  parent_job_id, config_path, bundle_blob_key,
                  snapshot_id, helix_runtime_version, run_label, attempt, summary, user_id
        """
    )
    try:
        with engine.begin() as conn:
            row = conn.execute(
                sql,
                {
                    "wid": settings.WORKER_ID,
                    "lease": str(settings.LEASE_DURATION_S),
                },
            ).mappings().first()
    except IntegrityError:
        return None
    return dict(row) if row else None


def fail_stale_queued_jobs() -> int:
    """Fail queued jobs that can never run in snapshot mode.

    A queued job with no snapshot_id (e.g. a legacy/baked submission, or a
    client that skipped publish) cannot be materialized. After a generous
    grace period mark it failed so it doesn't linger forever. Jobs pinned to
    an *absent* snapshot are handled separately: the worker claims them and
    parks them `blocked`, and re-publishing the snapshot unblocks them.
    """
    sql = text(
        """
        UPDATE jobs
        SET status='failed',
            ended_at=now(),
            exit_code=NULL,
            summary = COALESCE(summary, CAST('{}' AS jsonb))
                      || CAST('{"error":"queued_without_snapshot"}' AS jsonb)
        WHERE status='queued'
          AND snapshot_id IS NULL
          AND created_at < now() - interval '5 minutes'
        RETURNING id
        """
    )
    with engine.begin() as conn:
        return len(conn.execute(sql).all())


def reclaim_expired() -> int:
    """Finalize/requeue running jobs whose worker is gone.

    Two distinct cases:
      - cancel_requested=true → mark 'cancelled' (terminal). The user
        had asked to cancel, so we must NOT silently restart the job.
      - cancel_requested=false → put back to 'queued' for retry.
    """
    cancel_sql = text(
        """
        UPDATE jobs
        SET status='cancelled',
            ended_at = COALESCE(ended_at, now()),
            worker_id = NULL,
            lease_expires_at = NULL
        WHERE status='running'
          AND cancel_requested = true
          AND (lease_expires_at < now()
               OR worker_id NOT IN (
                 SELECT worker_id FROM worker_heartbeats
                 WHERE last_seen > now() - interval '30 seconds'
               ))
        RETURNING id
        """
    )
    requeue_sql = text(
        """
        UPDATE jobs
        SET status='queued', worker_id=NULL, lease_expires_at=NULL
        WHERE status='running'
          AND cancel_requested = false
          AND (lease_expires_at < now()
               OR worker_id NOT IN (
                 SELECT worker_id FROM worker_heartbeats
                 WHERE last_seen > now() - interval '30 seconds'
               ))
        RETURNING id
        """
    )
    with engine.begin() as conn:
        cancelled = conn.execute(cancel_sql).all()
        requeued = conn.execute(requeue_sql).all()
    return len(cancelled) + len(requeued)


def fence(sql: str, params: dict[str, Any], job_id, attempt: int) -> int:
    """Run an UPDATE/INSERT that is conditional on the worker still owning the job.

    The caller's `sql` must include `:_job_id_fence`, `:_worker_id_fence`,
    `:_attempt_fence` placeholders in a WHERE/EXISTS clause.
    Returns rowcount.
    """
    p = dict(params)
    p["_job_id_fence"] = job_id
    p["_worker_id_fence"] = settings.WORKER_ID
    p["_attempt_fence"] = attempt
    with engine.begin() as conn:
        result = conn.execute(text(sql), p)
        return result.rowcount or 0
