"""helix-worker entrypoint: poll Postgres for queued jobs and run them."""
from __future__ import annotations

import time

import structlog

from . import settings
from .claim import claim_next_job, fail_stale_queued_jobs, reclaim_expired
from .heartbeat import Heartbeat
from .runner import run_job


log = structlog.get_logger(__name__)


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
    )
    log.info(
        "worker_boot",
        worker_id=settings.WORKER_ID,
        baked_sha=settings.HELIX_BAKED_REPO_SHA,
    )

    # On boot, requeue any orphaned 'running' jobs.
    try:
        n = reclaim_expired()
        if n:
            log.info("recovered_expired_jobs", count=n)
    except Exception as e:  # noqa: BLE001
        log.warning("recovery_failed", error=str(e))

    hb = Heartbeat()
    hb.start()

    poll_interval = 1.0
    while True:
        try:
            job = claim_next_job()
        except Exception as e:  # noqa: BLE001
            log.warning("claim_failed", error=str(e))
            time.sleep(2.0)
            continue

        if job is None:
            # Opportunistic sweeps when idle.
            try:
                reclaim_expired()
            except Exception:
                pass
            try:
                stale = fail_stale_queued_jobs()
                if stale:
                    log.info("failed_stale_queued_jobs", count=stale)
            except Exception:
                pass
            time.sleep(poll_interval)
            continue

        hb.set_current_job(job["id"], job["attempt"])
        try:
            run_job(job)
        finally:
            hb.set_current_job(None, None)


if __name__ == "__main__":
    main()
