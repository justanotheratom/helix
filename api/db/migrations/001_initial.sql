-- Helix initial schema.
-- Loaded by postgres on first boot via /docker-entrypoint-initdb.d/.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- First-class concepts
-- ---------------------------------------------------------------------------

CREATE TABLE programs (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE program_versions (
    id          SERIAL PRIMARY KEY,
    program_id  INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    UNIQUE (program_id, version)
);

CREATE TABLE datasets (
    id                  SERIAL PRIMARY KEY,
    program_version_id  INTEGER NOT NULL REFERENCES program_versions(id) ON DELETE CASCADE,
    version             TEXT NOT NULL,
    UNIQUE (program_version_id, version)
);

CREATE TABLE splits (
    id          SERIAL PRIMARY KEY,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    UNIQUE (dataset_id, version)
);

-- ---------------------------------------------------------------------------
-- Jobs
-- ---------------------------------------------------------------------------

CREATE TABLE jobs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type                 TEXT NOT NULL CHECK (type IN ('compile','eval')),
    status               TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    program_version_id   INTEGER NOT NULL REFERENCES program_versions(id),
    dataset_id           INTEGER NOT NULL REFERENCES datasets(id),
    split_id             INTEGER NOT NULL REFERENCES splits(id),
    parent_job_id        UUID    REFERENCES jobs(id),
    config_path          TEXT,
    config_blob_key      TEXT,
    bundle_blob_key      TEXT,
    baked_sha            TEXT,                       -- NULL allowed only for imported jobs
    run_label            TEXT NOT NULL UNIQUE,
    attempt              INTEGER NOT NULL DEFAULT 0,
    worker_id            TEXT,
    lease_expires_at     TIMESTAMPTZ,
    emitted_run_number   INTEGER,
    export_run_number    INTEGER,
    -- Durable cancel intent. Set true by the API's cancel endpoint
    -- (in addition to the transient redis pub/sub signal). The claim
    -- query refuses jobs with cancel_requested=true; the recovery sweep
    -- marks them 'cancelled' rather than requeuing. The worker heartbeat
    -- re-publishes the redis cancel if it sees this flag mid-run, so a
    -- pub/sub message missed at job-start time still resolves.
    cancel_requested     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at           TIMESTAMPTZ,
    ended_at             TIMESTAMPTZ,
    exit_code            INTEGER,
    summary              JSONB,
    CHECK ( (type = 'eval') = (parent_job_id IS NOT NULL) )
);

CREATE INDEX idx_jobs_queued     ON jobs (created_at)        WHERE status = 'queued';
CREATE INDEX idx_jobs_running    ON jobs (lease_expires_at)  WHERE status = 'running';
CREATE INDEX idx_jobs_parent     ON jobs (parent_job_id)     WHERE parent_job_id IS NOT NULL;
CREATE INDEX idx_jobs_pv_status  ON jobs (program_version_id, status, created_at DESC);

-- Allocator-invariant uniqueness (belt-and-braces).
CREATE UNIQUE INDEX uq_jobs_compile_emitted
    ON jobs (program_version_id, emitted_run_number)
    WHERE type = 'compile' AND emitted_run_number IS NOT NULL;

CREATE UNIQUE INDEX uq_jobs_eval_emitted
    ON jobs (parent_job_id, emitted_run_number)
    WHERE type = 'eval' AND emitted_run_number IS NOT NULL;

CREATE UNIQUE INDEX uq_jobs_compile_export
    ON jobs (program_version_id, export_run_number)
    WHERE type = 'compile' AND export_run_number IS NOT NULL;

CREATE UNIQUE INDEX uq_jobs_eval_export
    ON jobs (parent_job_id, export_run_number)
    WHERE type = 'eval' AND export_run_number IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Workers
-- ---------------------------------------------------------------------------

CREATE TABLE worker_heartbeats (
    worker_id   TEXT PRIMARY KEY,
    baked_sha   TEXT NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Run-number allocators
-- next_number stores the VALUE THE NEXT ALLOCATION WILL RETURN.
-- Seed on first insert: max(observed)+1; the INSERT bumps to max+2.
-- ---------------------------------------------------------------------------

CREATE TABLE legacy_compile_run_numbers (
    program_version_id  INTEGER PRIMARY KEY REFERENCES program_versions(id) ON DELETE CASCADE,
    next_number         INTEGER NOT NULL CHECK (next_number > 0)
);

CREATE TABLE legacy_eval_run_numbers (
    compile_job_id  UUID PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    next_number     INTEGER NOT NULL CHECK (next_number > 0)
);

-- ---------------------------------------------------------------------------
-- Artifacts
-- ---------------------------------------------------------------------------

CREATE TABLE artifacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    relative_path  TEXT NOT NULL,
    kind           TEXT NOT NULL,
    blob_key       TEXT NOT NULL,
    size_bytes     BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256         CHAR(64) NOT NULL,
    mime           TEXT,
    attempt        INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, attempt, relative_path)
);

CREATE INDEX idx_artifacts_job_kind ON artifacts (job_id, kind);
