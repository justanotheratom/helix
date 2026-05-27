import os
import socket


HELIX_BAKED_REPO_SHA = os.environ.get("HELIX_BAKED_REPO_SHA", "generic")
HELIX_DATABASE_URL = os.environ.get(
    "HELIX_DATABASE_URL",
    "postgresql+psycopg://helix:helix-local-dev@helix-postgres:5432/helix",
)
HELIX_REDIS_URL = os.environ.get("HELIX_REDIS_URL", "redis://helix-redis:6379/0")
HELIX_BLOB_ENDPOINT = os.environ.get("HELIX_BLOB_ENDPOINT", "http://helix-minio:9000")
HELIX_BLOB_ACCESS_KEY = os.environ.get("HELIX_BLOB_ACCESS_KEY", "helix")
HELIX_BLOB_SECRET_KEY = os.environ.get("HELIX_BLOB_SECRET_KEY", "helix-local-dev-minio")
HELIX_BLOB_BUCKET = os.environ.get("HELIX_BLOB_BUCKET", "helix")

WORK_DIR = "/work"

# Generic image layout: the helix_runtime entrypoints are a fixed layer,
# NOT baked from any consumer repo. The consumer base dir + its .helix.toml
# arrive at runtime as a content-addressed snapshot (materialized per job);
# config is read from the snapshot's embedded .helix/config.toml, never a
# baked worktree file.
HELIX_RUNTIME_DIR = os.environ.get("HELIX_RUNTIME_DIR", "/helix-runtime")

# Concrete helix-runtime version this worker provides. A job carries the
# consumer's required spec (helix_runtime_version, e.g. ">=0.1,<0.2"); the
# worker refuses (blocks) a job whose spec this version doesn't satisfy.
HELIX_RUNTIME_VERSION = os.environ.get("HELIX_RUNTIME_VERSION", "0.1.0")

WORKER_ID = os.environ.get("HOSTNAME") or socket.gethostname()
HEARTBEAT_INTERVAL_S = 5
LEASE_DURATION_S = 30
