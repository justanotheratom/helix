"""Helix API entrypoint."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .routes import artifacts, gc, import_compile, jobs, logs, runtime, snapshots, traces
from .blob import ensure_bucket


app = FastAPI(
    title="Helix",
    version="0.1.0",
    description="Local DSPy compile/eval job runner",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    # Caddy proxies /api/* with `handle_path` (strips the prefix), so the
    # browser sees the app at /api but FastAPI's path is /. root_path tells
    # FastAPI to emit absolute URLs (incl. the openapi.json reference inside
    # Swagger UI) with the /api prefix the browser actually needs.
    root_path="/api",
)


@app.on_event("startup")
def _on_startup() -> None:
    # Best-effort: make sure the blob bucket exists before first request.
    try:
        ensure_bucket()
    except Exception:
        # Defer to first real request; postgres/minio may still be coming up.
        pass


@app.get("/openapi.yaml", response_class=PlainTextResponse)
def serve_openapi_yaml() -> str:
    """Serve the hand-edited spec verbatim. The /openapi.json above is FastAPI's
    derived view from route signatures and may drift from the YAML; the YAML is
    the source of truth."""
    spec_path = Path("/app/openapi.yaml")
    if spec_path.exists():
        return spec_path.read_text()
    return yaml.dump({})


app.include_router(jobs.router)
app.include_router(import_compile.router)
app.include_router(artifacts.router)
app.include_router(logs.router)
app.include_router(runtime.router)
app.include_router(snapshots.router)
app.include_router(gc.router)
app.include_router(traces.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
