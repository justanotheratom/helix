-- Helix Phase 2: content-addressed snapshots, multi-repo scoping, blocked state.
--
-- NOTE: postgres only auto-runs /docker-entrypoint-initdb.d/ on a FRESH
-- volume. For an existing dev DB, apply this file manually:
--     docker exec <pg> psql -U helix -d helix -f /docker-entrypoint-initdb.d/002_phase2_snapshots.sql
-- It is written to be idempotent (IF NOT EXISTS / guarded) so re-running is safe.

-- ---------------------------------------------------------------------------
-- Multi-repo scoping: a program belongs to a repo. Everything below it
-- (versions, datasets, splits, allocators) is repo-scoped transitively via
-- the FK chain, so repo_id only needs to live on `programs`.
-- ---------------------------------------------------------------------------

ALTER TABLE programs ADD COLUMN IF NOT EXISTS repo_id TEXT;
-- Backfill any pre-Phase-2 rows that lack a repo_id. Fresh installs have no
-- such rows; existing deployments get a 'legacy' placeholder which the
-- operator can update before introducing a second repo_id.
UPDATE programs SET repo_id = 'legacy' WHERE repo_id IS NULL;
ALTER TABLE programs ALTER COLUMN repo_id SET NOT NULL;

-- Replace the global UNIQUE(name) with UNIQUE(repo_id, name) so two repos
-- can each have a "calendar-event-agent".
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_name_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_programs_repo_name'
    ) THEN
        ALTER TABLE programs ADD CONSTRAINT uq_programs_repo_name UNIQUE (repo_id, name);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Snapshots manifest (content-addressed; digest is the identity).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS snapshots (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id               TEXT NOT NULL,
    digest                CHAR(64) NOT NULL,          -- sha256 of uncompressed tar
    git_sha               TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    helix_runtime_version TEXT NOT NULL,
    lockfile_digest       TEXT,
    base_fingerprint      TEXT,
    config_blob           TEXT NOT NULL,              -- the resolved .helix.toml (authoritative)
    seed_state            JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {"<program>/<version>": maxRunNumber}
    -- Many manifest rows may point at one digest (same tree, different commits),
    -- but the object key is digest-primary, so the blob is deduped.
    UNIQUE (repo_id, digest)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_digest ON snapshots (digest);

-- ---------------------------------------------------------------------------
-- Jobs: snapshot fence replaces baked_sha; multi-repo + blocked state.
-- ---------------------------------------------------------------------------

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS repo_id               TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS snapshot_id           UUID REFERENCES snapshots(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS helix_runtime_version TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS blocked_reason        TEXT;

-- Backfill repo_id on existing jobs from their program.
UPDATE jobs j
SET repo_id = p.repo_id
FROM program_versions pv
JOIN programs p ON p.id = pv.program_id
WHERE j.program_version_id = pv.id AND j.repo_id IS NULL;
UPDATE jobs SET repo_id = 'legacy' WHERE repo_id IS NULL;
ALTER TABLE jobs ALTER COLUMN repo_id SET NOT NULL;

-- Add 'blocked' to the status check.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('queued','running','succeeded','failed','cancelled','blocked'));

CREATE INDEX IF NOT EXISTS idx_jobs_repo ON jobs (repo_id, created_at DESC);
