"""Thin httpx wrapper for the Helix API.

Once `helix/openapi/codegen.sh` is wired, this becomes a re-export of
`helix_cli.generated.client` and we delete the hand-written calls below.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .config import HELIX_API_BASE


def _client() -> httpx.Client:
    return httpx.Client(base_url=HELIX_API_BASE, timeout=60.0)


def _check(resp: httpx.Response) -> Any:
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise SystemExit(f"helix API error {resp.status_code}: {body}")
    if not resp.content:
        return None
    return resp.json()


def get_baked_sha() -> dict[str, Any]:
    with _client() as c:
        return _check(c.get("/runtime/baked-sha"))


def submit_compile(metadata: dict[str, Any], bundle_bytes: bytes | None) -> list[dict[str, Any]]:
    files = {"metadata": (None, json.dumps(metadata), "application/json")}
    if bundle_bytes:
        files["bundle"] = ("bundle.tar.gz", bundle_bytes, "application/gzip")
    with _client() as c:
        return _check(c.post("/jobs/compile", files=files))


def submit_eval(metadata: dict[str, Any], bundle_bytes: bytes | None) -> list[dict[str, Any]]:
    files = {"metadata": (None, json.dumps(metadata), "application/json")}
    if bundle_bytes:
        files["bundle"] = ("bundle.tar.gz", bundle_bytes, "application/gzip")
    with _client() as c:
        return _check(c.post("/jobs/eval", files=files))


def import_compile(metadata: dict[str, Any], bundle_bytes: bytes) -> dict[str, Any]:
    files = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "bundle": ("results.tar.gz", bundle_bytes, "application/gzip"),
    }
    with _client() as c:
        return _check(c.post("/jobs/import-compile", files=files))


def resolve_snapshot(repo_id: str, digest: str) -> dict[str, Any] | None:
    with _client() as c:
        r = c.get("/snapshots/resolve", params={"repo_id": repo_id, "digest": digest})
        if r.status_code == 404:
            return None
        return _check(r)


def publish_oob(digest: str, tar_gz: bytes) -> dict[str, Any]:
    files = {
        "digest": (None, digest),
        "tarball": ("oob.tar.gz", tar_gz, "application/gzip"),
    }
    with _client() as c:
        return _check(c.post("/snapshots/oob", files=files))


def publish_snapshot(metadata: dict[str, Any], tar_gz: bytes) -> dict[str, Any]:
    files = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "tarball": ("snapshot.tar.gz", tar_gz, "application/gzip"),
    }
    with _client() as c:
        return _check(c.post("/snapshots", files=files))


def gc(grace_hours: int, dry_run: bool) -> dict[str, Any]:
    with _client() as c:
        return _check(
            c.post("/gc", params={"grace_hours": grace_hours, "dry_run": dry_run})
        )


def list_jobs(**params) -> list[dict[str, Any]]:
    with _client() as c:
        return _check(c.get("/jobs", params={k: v for k, v in params.items() if v is not None}))


def get_job(job_id: str) -> dict[str, Any]:
    with _client() as c:
        return _check(c.get(f"/jobs/{job_id}"))


def cancel_job(job_id: str) -> dict[str, Any]:
    with _client() as c:
        return _check(c.post(f"/jobs/{job_id}/cancel"))


def list_artifacts(job_id: str, **params) -> list[dict[str, Any]]:
    with _client() as c:
        return _check(c.get(f"/jobs/{job_id}/artifacts", params=params))


def stream_logs(job_id: str):
    """Yields decoded JSON lines from the SSE stream."""
    with httpx.stream("GET", f"{HELIX_API_BASE}/jobs/{job_id}/logs", timeout=None) as r:
        if r.status_code != 200:
            raise SystemExit(f"helix logs error {r.status_code}")
        for raw in r.iter_lines():
            if not raw or raw.startswith(":"):
                continue
            if raw.startswith("data: "):
                payload = raw[6:]
                try:
                    yield json.loads(payload)
                except Exception:
                    yield {"line": payload}


def download_artifacts_tar(job_id: str, dest_path: str, prefix: str | None = None) -> None:
    params = {"prefix": prefix} if prefix else {}
    with httpx.stream(
        "GET",
        f"{HELIX_API_BASE}/jobs/{job_id}/artifacts.tar.gz",
        params=params,
        timeout=None,
    ) as r:
        if r.status_code != 200:
            raise SystemExit(f"helix download error {r.status_code}: {r.read().decode(errors='replace')}")
        with open(dest_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
