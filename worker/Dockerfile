# helix-worker Dockerfile — GENERIC, repo-agnostic.
# Carries Helix infra deps + uv + the helix_runtime entrypoints only. NO
# consumer repo is baked: the worker materializes a content-addressed
# snapshot per job (lowerdir) and builds the job's env from the snapshot's
# uv.lock via `uv sync` (the venv supplies dspy/langfuse/litellm/etc.).
#
# Deps are pinned by the workspace `uv.lock` at the repo root; this Dockerfile
# pins nothing inline. Helix source still arrives via PYTHONPATH, not as an
# installed wheel, to keep the dev bind-mount loop simple.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libpq5 git && \
    rm -rf /var/lib/apt/lists/*

# Bootstrap uv (we'll re-install the lockfile version below).
RUN pip install --no-cache-dir uv

# --- Resolve helix-worker deps from the workspace lockfile -------------------
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/
COPY worker/pyproject.toml worker/
COPY cli/pyproject.toml cli/
COPY common/pyproject.toml common/
# uv sync needs the helix-common source on disk so its workspace entry resolves.
COPY common/helix_config.py common/
RUN uv sync --frozen --package helix-worker --no-install-workspace

ENV VIRTUAL_ENV=/workspace/.venv \
    PATH=/workspace/.venv/bin:$PATH

# --- Helix source via PYTHONPATH (unchanged pattern) -------------------------
WORKDIR /app
COPY common/helix_config.py /app/helix_config.py
COPY worker /app/helix_worker_pkg
COPY runtime /helix-runtime

# Per-job overlay workdir + content-addressed snapshot/oob/venv caches.
RUN mkdir -p /work /var/lib/helix/snapshots /var/lib/helix/oob /var/lib/helix/venvs
VOLUME ["/work", "/var/lib/helix/snapshots", "/var/lib/helix/oob", "/var/lib/helix/venvs"]

ENV PYTHONPATH=/app
ENV HELIX_RUNTIME_DIR=/helix-runtime
CMD ["python", "-m", "helix_worker_pkg.helix_worker.main"]
