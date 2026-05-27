# helix-api Dockerfile — GENERIC, repo-agnostic.
# No consumer repo is baked: program/version inference + config come from the
# submission's snapshot manifest (config_blob), not a worktree file.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only the API's own dependencies first (cached layer).
COPY api/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir \
        "fastapi>=0.115" "uvicorn[standard]>=0.30" \
        "sqlalchemy>=2.0" "psycopg[binary]>=3.2" \
        "pydantic>=2.7" "pydantic-settings>=2.4" \
        "minio>=7.2" "redis>=5.0" "httpx>=0.27" \
        "python-multipart>=0.0.9" \
        "anyio>=4.4" "structlog>=24.1" "PyYAML>=6.0"

# Shared config loader (importable as `helix_config`; PYTHONPATH=/app).
COPY common/helix_config.py /app/helix_config.py

# API source + OpenAPI spec.
COPY api /app/helix_api_pkg
COPY openapi/openapi.yaml /app/openapi.yaml

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "helix_api_pkg.helix_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
