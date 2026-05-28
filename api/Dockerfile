# helix-api Dockerfile — GENERIC, repo-agnostic.
# No consumer repo is baked: program/version inference + config come from the
# submission's snapshot manifest (config_blob), not a worktree file.
#
# Deps are pinned by the workspace `uv.lock` at the repo root; this Dockerfile
# pins nothing inline. API source still arrives via PYTHONPATH (helix_api_pkg).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libpq5 && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# --- Resolve helix-api deps from the workspace lockfile ----------------------
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/
COPY worker/pyproject.toml worker/
COPY cli/pyproject.toml cli/
COPY common/pyproject.toml common/
COPY common/helix_config.py common/
RUN uv sync --frozen --package helix-api --no-install-workspace

ENV VIRTUAL_ENV=/workspace/.venv \
    PATH=/workspace/.venv/bin:$PATH

# --- API source via PYTHONPATH (unchanged pattern) ---------------------------
WORKDIR /app
COPY common/helix_config.py /app/helix_config.py
COPY api /app/helix_api_pkg
COPY openapi/openapi.yaml /app/openapi.yaml

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "helix_api_pkg.helix_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
