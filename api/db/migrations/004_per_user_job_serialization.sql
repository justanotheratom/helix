-- Helix Phase 4: serialize queued work per submitting user instead of globally.
--
-- Jobs carry a user_id so the worker can run jobs from different users in
-- parallel while still keeping each user's jobs in submission order. The
-- partial unique index is the race-proof guard: even if two workers try to
-- claim adjacent queued jobs for the same user concurrently, Postgres permits
-- only one row for that user to be in status='running'.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id TEXT;

UPDATE jobs
SET user_id = 'legacy'
WHERE user_id IS NULL OR btrim(user_id) = '';

ALTER TABLE jobs ALTER COLUMN user_id SET DEFAULT 'anonymous';
ALTER TABLE jobs ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_user_status_created
    ON jobs (user_id, status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_running_per_user
    ON jobs (user_id)
    WHERE status = 'running';
