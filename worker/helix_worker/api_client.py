"""Minimal compose-internal client for the worker to talk back to helix-api.

Used only for auto-eval chaining today; if we add more worker→api
round-trips, this is the file to grow.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx


HELIX_API_INTERNAL = os.environ.get("HELIX_API_INTERNAL", "http://helix-api:8000")


def submit_eval(
    *, repo_id: str, config_path: str, compile_job_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Auto-chain: ask helix-api to enqueue an eval against the just-finished compile.

    The eval bundle is empty — the parent compile already shipped the overlay;
    the API inherits repo_id/snapshot/runtime + the parent's bundle bytes from
    the parent compile job.
    """
    metadata = {
        "repo_id": repo_id,
        "configs": [
            {
                "config_path": config_path,
                "compile_job_id": str(compile_job_id),
            }
        ],
        "overlay_files": [],
        "inherit_bundle_from_compile_job_id": str(compile_job_id),
    }
    files = {"metadata": (None, json.dumps(metadata), "application/json")}
    with httpx.Client(base_url=HELIX_API_INTERNAL, timeout=30.0) as c:
        resp = c.post("/jobs/eval", files=files)
        resp.raise_for_status()
        return resp.json()
