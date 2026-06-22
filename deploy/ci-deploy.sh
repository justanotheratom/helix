#!/usr/bin/env bash
# Deploy Helix from a checked-out working tree on the server.
#
# The deploy is intentionally conservative around active jobs:
# - build images while jobs may still be running
# - apply DB migrations before new code starts
# - wait for running jobs to drain before restarting services
# - stop workers only after the drain, so queued jobs wait for the new worker

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DEPLOY_DIR="$ROOT/deploy"

IFS=' ' read -r -a COMPOSE_FILES <<< "${HELIX_COMPOSE_FILES:-docker-compose.yml docker-compose.prod.yml docker-compose.cloudflare.yml}"
DRAIN_TIMEOUT_SECONDS="${HELIX_DEPLOY_DRAIN_TIMEOUT_SECONDS:-3600}"
DRAIN_POLL_SECONDS="${HELIX_DEPLOY_DRAIN_POLL_SECONDS:-15}"
DEPLOYMENT_DRAIN_REASON="deployment_drain"

compose() {
    local args=()
    for file in "${COMPOSE_FILES[@]}"; do
        args+=("-f" "$file")
    done
    docker compose "${args[@]}" --env-file .env "$@"
}

psql() {
    compose exec -T helix-postgres psql -U helix -d helix "$@"
}

query_scalar() {
    psql -At -v ON_ERROR_STOP=1 -c "$1"
}

wait_for_postgres() {
    local deadline=$((SECONDS + 120))
    until compose exec -T helix-postgres pg_isready -U helix -d helix >/dev/null 2>&1; do
        if (( SECONDS >= deadline )); then
            echo "helix-postgres did not become ready in time" >&2
            return 1
        fi
        sleep 2
    done
}

mark_existing_migrations() {
    psql -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS helix_schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO helix_schema_migrations (filename)
SELECT '001_initial.sql'
WHERE to_regclass('public.jobs') IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO helix_schema_migrations (filename)
SELECT '002_phase2_snapshots.sql'
WHERE to_regclass('public.snapshots') IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'jobs' AND column_name = 'snapshot_id'
  )
ON CONFLICT DO NOTHING;

INSERT INTO helix_schema_migrations (filename)
SELECT '003_phase3_oob.sql'
WHERE EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'snapshots' AND column_name = 'oob_blobs'
)
ON CONFLICT DO NOTHING;

INSERT INTO helix_schema_migrations (filename)
SELECT '004_per_user_job_serialization.sql'
WHERE EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'jobs' AND column_name = 'user_id'
)
ON CONFLICT DO NOTHING;
SQL
}

apply_migrations() {
    mark_existing_migrations

    local migration filename applied
    for migration in "$ROOT"/api/db/migrations/*.sql; do
        filename="$(basename "$migration")"
        applied="$(query_scalar "SELECT 1 FROM helix_schema_migrations WHERE filename = '$filename'")"
        if [[ "$applied" == "1" ]]; then
            echo "migration already applied: $filename"
            continue
        fi

        echo "applying migration: $filename"
        psql -v ON_ERROR_STOP=1 < "$migration"
        psql -v ON_ERROR_STOP=1 -c \
            "INSERT INTO helix_schema_migrations (filename) VALUES ('$filename') ON CONFLICT DO NOTHING"
    done
}

running_jobs_count() {
    query_scalar "SELECT count(*) FROM jobs WHERE status = 'running'"
}

park_queued_jobs_for_deploy() {
    psql -v ON_ERROR_STOP=1 -c \
        "UPDATE jobs
         SET status = 'blocked',
             blocked_reason = '$DEPLOYMENT_DRAIN_REASON'
         WHERE status = 'queued'
           AND cancel_requested = false
         RETURNING id, type, created_at"
}

unpark_deployment_drain_jobs() {
    psql -v ON_ERROR_STOP=1 -c \
        "UPDATE jobs
         SET status = 'queued',
             blocked_reason = NULL
         WHERE status = 'blocked'
           AND blocked_reason = '$DEPLOYMENT_DRAIN_REASON'
         RETURNING id, type, created_at"
}

wait_for_running_jobs_to_drain() {
    local deadline=$((SECONDS + DRAIN_TIMEOUT_SECONDS))
    local running

    while true; do
        # Keep old workers from grabbing queued jobs while this deploy waits for
        # already-running jobs to finish. The EXIT trap below restores them.
        park_queued_jobs_for_deploy
        running="$(running_jobs_count)"
        if [[ "$running" == "0" ]]; then
            echo "no running jobs; safe to restart workers"
            return 0
        fi

        if (( SECONDS >= deadline )); then
            echo "timed out waiting for $running running job(s) to finish" >&2
            echo "deploy aborted; rerun after the jobs complete or increase HELIX_DEPLOY_DRAIN_TIMEOUT_SECONDS" >&2
            return 1
        fi

        echo "waiting for $running running job(s) to finish..."
        sleep "$DRAIN_POLL_SECONDS"
    done
}

main() {
    cd "$ROOT"
    bash deploy/build.sh

    cd "$DEPLOY_DIR"
    trap unpark_deployment_drain_jobs EXIT
    compose up -d helix-postgres helix-minio helix-redis
    wait_for_postgres
    apply_migrations

    compose build helix-api helix-worker helix-ui
    wait_for_running_jobs_to_drain

    # Prevent a queued job from starting on the old worker during the restart.
    compose stop helix-worker || true
    compose up -d --remove-orphans
    unpark_deployment_drain_jobs
    trap - EXIT
    compose ps
}

main "$@"
