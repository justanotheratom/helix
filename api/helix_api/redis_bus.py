"""Redis pub/sub for live log streaming and cancel signals.

Channels:
- helix:logs:<job_id>    — workers publish LogEvent JSON lines
- helix:cancel:<job_id>  — API publishes "1" to request cancel
"""
from __future__ import annotations

import redis

from .settings import settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def publish_cancel(job_id: str) -> int:
    return get_redis().publish(f"helix:cancel:{job_id}", "1")


def logs_channel(job_id: str) -> str:
    return f"helix:logs:{job_id}"
