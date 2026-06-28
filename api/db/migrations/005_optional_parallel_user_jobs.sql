-- Helix Phase 5: opt-in per-job bypass for per-user serialization.
--
-- By default, queued work remains serialized per submitting user. A job marked
-- allow_parallel_user_jobs=true may run even while another job for the same
-- user is already running. The unique guard therefore applies only to
-- non-parallel running jobs.

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS allow_parallel_user_jobs BOOLEAN NOT NULL DEFAULT false;

DROP INDEX IF EXISTS uq_jobs_running_per_user;

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_running_serial_per_user
    ON jobs (user_id)
    WHERE status = 'running' AND allow_parallel_user_jobs = false;
