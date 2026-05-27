# helix-worker Dockerfile — GENERIC, repo-agnostic.
# Carries Helix infra deps + uv + the helix_runtime entrypoints only. NO
# consumer repo is baked: the worker materializes a content-addressed
# snapshot per job (lowerdir) and builds the job's env from the snapshot's
# uv.lock via `uv sync` (the venv supplies dspy/langfuse/litellm/etc.).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libpq5 git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Helix infra deps only (the WORKER process). The job's Python deps are NOT
# here — they come from the per-snapshot consumer venv built by `uv sync`.
RUN pip install --no-cache-dir \
        "sqlalchemy>=2.0" "psycopg[binary]>=3.2" \
        "minio>=7.2" "redis>=5.0" "httpx>=0.27" \
        "pydantic>=2.7" "PyYAML>=6.0" "structlog>=24.1"

# uv: builds + caches the content-addressed consumer venv at runtime.
RUN pip install --no-cache-dir "uv>=0.5"

# Shared config loader (importable as `helix_config`; PYTHONPATH=/app).
COPY common/helix_config.py /app/helix_config.py

# Helix worker package.
COPY worker /app/helix_worker_pkg

# Helix runtime entrypoints — generic layer, run by the consumer venv's
# python with PYTHONPATH=<merged-snapshot-root>:/helix-runtime.
COPY runtime /helix-runtime

# Per-job overlay workdir + content-addressed snapshot/oob/venv caches.
RUN mkdir -p /work /var/lib/helix/snapshots /var/lib/helix/oob /var/lib/helix/venvs
VOLUME ["/work", "/var/lib/helix/snapshots", "/var/lib/helix/oob", "/var/lib/helix/venvs"]

ENV PYTHONPATH=/app
ENV HELIX_RUNTIME_DIR=/helix-runtime
CMD ["python", "-m", "helix_worker_pkg.helix_worker.main"]
