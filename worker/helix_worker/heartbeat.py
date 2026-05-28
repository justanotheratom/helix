"""Background thread: UPSERT worker_heartbeats every 5s; extend the
current job's lease at the same cadence."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

import redis as redis_lib
import structlog
from sqlalchemy import text

from . import progress_parser, settings
from .db import engine


log = structlog.get_logger(__name__)


class Heartbeat:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._current_job: uuid.UUID | None = None
        self._current_attempt: int | None = None
        self._thread = threading.Thread(target=self._run, name="helix-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def set_current_job(self, job_id: uuid.UUID | None, attempt: int | None) -> None:
        self._current_job = job_id
        self._current_attempt = attempt

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:  # never let the heartbeat thread die
                log.warning("heartbeat_tick_failed", error=str(e))
            self._stop.wait(settings.HEARTBEAT_INTERVAL_S)

    def _tick(self) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO worker_heartbeats (worker_id, baked_sha, last_seen)
                    VALUES (:wid, :sha, now())
                    ON CONFLICT (worker_id) DO UPDATE
                      SET baked_sha = EXCLUDED.baked_sha, last_seen = now()
                    """
                ),
                {"wid": settings.WORKER_ID, "sha": settings.HELIX_BAKED_REPO_SHA},
            )
            if self._current_job is not None:
                conn.execute(
                    text(
                        """
                        UPDATE jobs
                        SET lease_expires_at = now() + CAST(:lease || ' seconds' AS interval)
                        WHERE id = :jid AND worker_id = :wid AND attempt = :att
                        """
                    ),
                    {
                        "lease": str(settings.LEASE_DURATION_S),
                        "jid": self._current_job,
                        "wid": settings.WORKER_ID,
                        "att": self._current_attempt,
                    },
                )
                # Re-observe durable cancel intent. If the API's redis
                # publish missed (worker booted between job-start and the
                # publish), this picks it up. Republishing is a no-op when
                # the subprocess is already gone.
                row = conn.execute(
                    text(
                        "SELECT cancel_requested FROM jobs WHERE id = :jid"
                    ),
                    {"jid": self._current_job},
                ).first()
                if row and row[0]:
                    self._republish_cancel(self._current_job)

                # Publish a live progress snapshot into jobs.summary so the
                # home/list view can show real progress per running row
                # without per-row log streaming on the client.
                self._publish_progress(conn, self._current_job)

    def _publish_progress(self, conn, job_id: uuid.UUID) -> None:
        log_path = os.path.join("/work", str(job_id), "stdout.log")
        try:
            prog = progress_parser.parse_file(log_path)
        except Exception as e:  # noqa: BLE001 — never let parsing kill the heartbeat
            log.warning("progress_parse_failed", error=str(e))
            return
        if not prog:
            return
        try:
            conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET summary = COALESCE(summary, CAST('{}' AS jsonb))
                                  || jsonb_build_object('progress', CAST(:p AS jsonb))
                    WHERE id = :jid AND worker_id = :wid AND attempt = :att
                    """
                ),
                {
                    "p": json.dumps(prog),
                    "jid": job_id,
                    "wid": settings.WORKER_ID,
                    "att": self._current_attempt,
                },
            )
        except Exception as e:  # noqa: BLE001
            log.warning("progress_write_failed", error=str(e))

    def _republish_cancel(self, job_id: uuid.UUID) -> None:
        try:
            r = redis_lib.Redis.from_url(settings.HELIX_REDIS_URL, decode_responses=True)
            r.publish(f"helix:cancel:{job_id}", "1")
        except Exception as e:  # noqa: BLE001
            log.warning("heartbeat_republish_cancel_failed", error=str(e))
