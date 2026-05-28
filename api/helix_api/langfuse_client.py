"""Thin async client for Langfuse's public REST API.

Helix-internal-only: helix-api reads traces from langfuse-web on the docker
network using the same project public/secret keys the worker uses to publish.
The browser never talks to Langfuse directly — the Helix UI hits helix-api,
which proxies the parts we want to expose.
"""
from __future__ import annotations

from typing import Any

import httpx

from .settings import langfuse_settings


def _auth() -> tuple[str, str]:
    return (
        langfuse_settings.langfuse_init_project_public_key,
        langfuse_settings.langfuse_init_project_secret_key,
    )


def _base() -> str:
    return langfuse_settings.langfuse_internal_base_url.rstrip("/")


async def list_traces(
    *,
    environment: str | None = None,
    limit: int = 50,
    page: int = 1,
    from_timestamp: str | None = None,
) -> dict[str, Any]:
    """Return Langfuse's paginated list of traces, optionally filtered by
    `environment` (the run_label Helix tags every span with)."""
    params: dict[str, Any] = {"limit": limit, "page": page, "orderBy": "timestamp.desc"}
    if environment:
        params["environment"] = environment
    if from_timestamp:
        params["fromTimestamp"] = from_timestamp
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{_base()}/api/public/traces", params=params, auth=_auth())
        r.raise_for_status()
        return r.json()


async def get_trace(trace_id: str) -> dict[str, Any]:
    """Single trace with observations nested. Returns the raw Langfuse payload."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{_base()}/api/public/traces/{trace_id}", auth=_auth())
        r.raise_for_status()
        return r.json()
