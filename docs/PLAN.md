# Helix — Compile/Eval Job Runner Service

## PRD

### Problem

DSPy compile and eval are central to our model-quality workflow, but their
runtime today is a hand-rolled launcher (`launch_compile_eval.py`) that
shells out to `uv run` on the host, writes logs to `/tmp`, registers them
in a flat-file viewer, and writes results into the git-tracked repo tree.
There is no durable record of what was run, no first-class concept of
program / version / dataset / split, no easy way to compare runs, and
investigating an issue requires hopping between three tools (the log
file, the progress viewer, Langfuse).

### Goal

Ship a single, locally-hosted service — **Helix** — that owns the entire
compile/eval job lifecycle: submission, execution, observability, and
artifact storage. One URL, one CLI, one source of truth.

### Users

A single local developer (and Claude-Code-driven agents acting on their
behalf). No multi-user auth in v1. Bind everything to `127.0.0.1`.

### v1 user stories

1. *As the developer*, I run `helix bootstrap` once on a new laptop and
   `helix up` to bring the whole stack online; I never edit a compose
   file by hand.
2. *As the developer*, I run
   `helix submit compile <yaml> [<yaml>…]` (positional configs; multi-submit
   supported) and immediately get one `{job_id, run_label, ui_url,
   langfuse_url}` per submitted job.
3. *As the developer*, I can `helix list` to see every compile and eval
   ever run, filtered by program/version/dataset/split/status.
4. *As the developer*, when investigating a regression I can click from
   the job detail page directly into the Langfuse traces for that job —
   no manual environment-tag copy-paste.
5. *As the developer*, I can `helix cancel <id>` to immediately stop a
   runaway eval; partial artifacts are kept for forensics.
6. *As the developer*, I can run an eval against an earlier compile by id
   (`helix submit eval <yaml> --compile-job <uuid>`); Helix supplies the
   compiled program; lineage is recorded.
7. *As Claude*, when invoked via the `/ai-compile` or `/ai-eval` skill, I
   call `helix submit …` under the hood; the user's mental model of the
   skills doesn't change but the runtime is now Helix.

### Non-goals (v1)

- Authentication, multi-user, remote/hosted access (LAN or beyond).
- Concurrent-job admission control / queue prioritisation beyond
  configurable worker replica count.
- Run-comparison / metric-diff UI. Defer; deep-link to existing
  EVAL_SUMMARY.md is enough.
- Artifact retention policies; v1 keeps everything forever, manual
  prune is acceptable.
- Re-implementing `compile.py` / `evaluate.py`; we treat them as the
  worker's payload and ship them inside the worker image unchanged.

### First-class concepts

Every job is tagged with **program**, **program version**, **dataset
version**, **split version**, recorded as foreign keys in the job table.
Lineage between eval and its parent compile is also a FK. These are the
dimensions every list / filter / report works on.

### Success criteria

- `launch_compile_eval.py`, `progress_viewer.{py,html}`, the standalone
  `langfuse/docker-compose.yml`, and `/tmp/kincalendar_ai_*` files are
  deleted from the repo.
- A single command (`helix submit compile …`) replaces the entire
  current launch path; `/ai-compile` and `/ai-eval` skill behaviour from
  the user's perspective is preserved or improved.
- All previously-runnable compile and eval configs run unchanged on
  Helix; outputs (program.pkl, results.jsonl, gepa_logs, EVAL_SUMMARY)
  are byte-equivalent (modulo timestamps).
- `helix down && helix up` preserves the full job history and all
  artifacts.
- A new developer can clone the repo, run `helix bootstrap && helix up
  && helix submit compile …`, and have a working compile finishing with
  traces in Langfuse — no further setup steps.

## Context

Today, DSPy compile and eval jobs are kicked off via
`.claude/skills/ai-utils/launch_compile_eval.py`, which:
- shells out to `uv run` on the host
- writes logs to `/tmp/*.log`
- registers them in a flat-file progress viewer manifest
- boots a dedicated local Langfuse stack
- writes results to `backend/ai/programs/<name>/<ver>/results/<NNNN>/`

This works for one developer on one laptop. It does not give us:
- a queryable history of jobs (status, lineage, metrics)
- a stable artifact store decoupled from the repo working tree
- a single UI that combines run status + Langfuse traces
- a clean way to cancel and reproduce a job
- awareness of `program / program-version / dataset-version / split-version`
  as first-class concepts

**Helix** is a self-contained, locally-hosted, docker-compose-based service
that owns the entire compile/eval lifecycle. It replaces
`launch_compile_eval.py` outright. The existing `/ai-compile` and `/ai-eval`
skills stay (same user-facing UX), but internally call the new `helix` CLI.

## Architecture

### Stack (one `docker-compose.yml`)

| Service       | Image / build                       | Role                                                            | Port (127.0.0.1) |
|---------------|-------------------------------------|-----------------------------------------------------------------|------------------|
| caddy         | `caddy:2`                           | Reverse proxy: `/api/*` → api, `/langfuse/*` → langfuse-web, `/langfuse-media/*` → langfuse minio (S3 media), `/` → ui. | **7000** (the *only* user-facing port) |
| helix-api     | local build (FastAPI, Python)       | Job CRUD, bundle upload, log streaming, dispatch                | internal         |
| helix-ui      | local build (Next.js SPA)           | Job list + detail + trace deep-links                            | internal         |
| helix-worker  | local build (Python + dspy stack + **baked repo snapshot**) | Long-running; claims jobs from Postgres, overlays bundle into repo snapshot, runs compile.py/evaluate.py, streams logs, uploads artifacts. Scaled 1–N replicas via compose `deploy.replicas`. | none             |
| helix-db      | `postgres:17`                       | Job metadata, lineage, artifact index, **job queue** (claimed via `FOR UPDATE SKIP LOCKED`) | internal |
| helix-blob    | `minio`                             | Job bundles + artifacts (logs, results.jsonl, program.pkl, gepa_logs) | internal         |
| helix-redis   | `redis:7`                           | **Non-durable signals only:** log pub/sub channels + cancel notifications. Job ownership is *not* in redis. | internal |
| langfuse-web / -worker / its own pg / clickhouse / minio / redis | (existing compose, folded in as services in the unified `docker-compose.yml`) | Trace store, **reached only through Caddy under `/langfuse/`**; no direct loopback port. | none (internal) |

Caddy fronts the entire stack on `127.0.0.1:7000`. One URL to remember,
one cookie origin, one place to attach future TLS.

### Langfuse subpath hosting + auto-SSO

Langfuse-web is a Next.js app and requires a NextAuth session. Helix
mints that session server-side so the user never sees a login screen.

**Compose env changes for subpath hosting** (in addition to the
existing `LANGFUSE_INIT_*` bootstrap values):
- `NEXTAUTH_URL=http://127.0.0.1:7000/langfuse` (replaces the existing `http://localhost:3010`).
- `LANGFUSE_BASE_PATH=/langfuse` (build- or run-time base path; Langfuse v3 supports it but the langfuse-web image MUST be one built with that flag — pin the exact image tag known-good for subpath hosting, or build a thin local layer that sets `NEXT_PUBLIC_BASE_PATH` and rebuilds).
- `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT=http://127.0.0.1:7000/langfuse-media` (so pre-signed media URLs given to the browser route through Caddy).
- `NEXTAUTH_TRUST_HOST=true` (NextAuth honours the proxied host).

**Caddyfile sketch:**
```
:7000 {
    # Helix surface
    handle_path /api/* { reverse_proxy helix-api:8000 }
    handle      /langfuse/* { reverse_proxy langfuse-web:3000 }
    handle      /langfuse-media/* {
        uri strip_prefix /langfuse-media
        reverse_proxy langfuse-minio:9000
    }
    handle { reverse_proxy helix-ui:3000 }   # SPA at /
}
```

**Auto-SSO endpoint (Helix API):**
- `GET /api/langfuse/sso?return_to=<path>` performs:
  1. POST credentials (from compose env, never user-visible) to
     `http://langfuse-web:3000/api/auth/callback/credentials` using
     the compose-internal hostname.
  2. Capture the `Set-Cookie` (`next-auth.session-token`, ~30-day
     lifetime).
  3. Return `302 Location: <return_to>` with the captured
     `Set-Cookie` attached. Same-origin under `:7000` ⇒ the cookie
     binds to `/langfuse/*` on the user's browser.
- **Silent re-mint on every click.** The endpoint *always* POSTs
  fresh and attaches a new cookie, regardless of whether the browser
  already has one. Cheap (one internal POST), eliminates the cookie-
  expiry edge case, and means clearing cookies in the browser never
  surfaces a Langfuse login screen.
- The Helix UI's "Open in Langfuse" button always goes through this
  endpoint; the trace deep-link API
  (`GET /api/jobs/{id}/traces`) returns a URL pointing at
  `/api/langfuse/sso?return_to=<langfuse-deep-link>`.

**Verification** (must pass before v1 ships):
- Click "Open in Langfuse" from a fresh incognito window → lands on
  the traces page already authenticated.
- Open a trace with a media attachment → media loads via
  `/langfuse-media/...` (no requests to `localhost:3010` or `:9090`).
- Clear cookies, click again → silent re-mint, no login screen.

### Repo layout

```
.claude/skills/ai-utils/helix/
├── docker-compose.yml          # full stack (folds in current langfuse compose)
├── Caddyfile
├── .env.example                # filled by `helix bootstrap`
├── api/                        # FastAPI
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── helix_api/
│       ├── main.py             # FastAPI app
│       ├── db.py               # SQLAlchemy session
│       ├── models.py           # ORM tables (see Data model below)
│       ├── schemas.py          # Pydantic request/response
│       ├── routes/             # /jobs, /artifacts, /logs (SSE), /traces
│       ├── dispatch.py         # INSERT job row (status='queued'); publish redis cancel
│       ├── blob.py             # minio client wrapper
│       └── langfuse_link.py    # build /api/langfuse/sso?return_to=/langfuse/project/<id>/traces?environment=… URL (auto-SSO trampoline)
├── worker/
│   ├── Dockerfile              # bakes python + dspy + litellm + openinference + the existing compile.py / evaluate.py
│   ├── pyproject.toml
│   └── helix_worker/
│       ├── main.py             # poll loop: Postgres claim (FOR UPDATE SKIP LOCKED) + heartbeat thread → run job → upload artifacts
│       ├── runner.py           # overlayfs mount (lowerdir=/repo-snapshot ro, upperdir/workdir on tmpfs) → /work/<job-id>/repo; cp -R fallback. Extract bundle on top, set env (incl. KIN_AI_RUN_LABEL), spawn compile.py / evaluate.py from inside the overlay, tee stdout/stderr to redis pub/sub + local log file (uploaded on completion). NEVER use cp -al.
│       ├── recovery.py         # on boot: requeue jobs whose lease has expired
│       └── cancel.py           # subscribe to redis cancel channel; SIGKILL the subprocess
├── ui/                         # Next.js SPA
│   ├── Dockerfile
│   ├── package.json
│   └── app/                    # pages: /, /jobs/[id]
├── cli/                        # `helix` CLI, distributed via uv tool
│   ├── pyproject.toml
│   └── helix_cli/
│       ├── __main__.py         # entry: `helix <subcommand>`
│       ├── bootstrap.py        # interactive secrets prompt → writes .env
│       ├── stack.py            # `helix up/down/status`
│       ├── submit.py           # `helix submit compile|eval ...`
│       ├── bundle.py           # computes overlay tarball (see "Overlay capture rules" below): config file + tracked diffs vs baked_sha + untracked files under overlayable roots
│       ├── jobs.py             # list/status/cancel/logs
│       └── open.py             # `helix open <id>` → opens UI
```

The existing `.claude/skills/ai-utils/launch_compile_eval.py`,
`progress_viewer.html`, `progress_viewer.py`, the standalone
`.claude/skills/ai-utils/langfuse/docker-compose.yml`, and the
`/tmp/kincalendar_ai_*` manifest files are **removed** as part of the cutover.

### Data model (`helix-db` Postgres)

```
programs           (id, name UNIQUE)
program_versions   (id, program_id, version, UNIQUE(program_id, version))
datasets           (id, program_version_id, version, UNIQUE(program_version_id, version))
splits             (id, dataset_id, version, UNIQUE(dataset_id, version))

jobs (
  id UUID PK,
  type TEXT,                          -- 'compile' | 'eval'
  status TEXT,                        -- 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  program_version_id FK,
  dataset_id FK,
  split_id FK,
  parent_job_id UUID NULL,            -- eval → its compile
  config_blob_key TEXT,
  bundle_blob_key TEXT,
  baked_sha TEXT,                     -- worker image's repo SHA when job was submitted
  run_label TEXT UNIQUE,              -- 40-char Langfuse env tag
  attempt INT DEFAULT 0,              -- incremented on each requeue
  worker_id TEXT NULL,                -- container hostname of current owner
  lease_expires_at TIMESTAMPTZ NULL,  -- claim is valid until this; heartbeat extends it
  emitted_run_number INT NULL,        -- the NNNN the worker actually emitted into blob storage. IMMUTABLE after the job completes. Allocated at job start; used as the path inside blob storage and in cross-job references (e.g. eval→compile lookup).
  export_run_number  INT NULL,        -- the NNNN used the last time `helix export` materialized this job onto the host. May differ from emitted_run_number if a manual/non-Helix run later occupied emitted_run_number on disk and forced renumbering at export time. Mutable; updated by `helix export`. Never used to locate blob artifacts.
  created_at, started_at, ended_at TIMESTAMPTZ,
  exit_code INT NULL,
  summary JSONB
);
CREATE INDEX ON jobs (status, created_at) WHERE status = 'queued';
CREATE INDEX ON jobs (status, lease_expires_at) WHERE status = 'running';

-- Allocator-invariant uniqueness: belt-and-braces against any future
-- allocator bug. Partial because eval jobs use parent_job_id keyspace
-- while compile jobs use program_version_id keyspace.
CREATE UNIQUE INDEX uq_jobs_compile_emitted ON jobs (program_version_id, emitted_run_number)
  WHERE type = 'compile' AND emitted_run_number IS NOT NULL;
CREATE UNIQUE INDEX uq_jobs_eval_emitted    ON jobs (parent_job_id, emitted_run_number)
  WHERE type = 'eval'    AND emitted_run_number IS NOT NULL;
CREATE UNIQUE INDEX uq_jobs_compile_export  ON jobs (program_version_id, export_run_number)
  WHERE type = 'compile' AND export_run_number IS NOT NULL;
CREATE UNIQUE INDEX uq_jobs_eval_export     ON jobs (parent_job_id, export_run_number)
  WHERE type = 'eval'    AND export_run_number IS NOT NULL;

worker_heartbeats (
  worker_id TEXT PRIMARY KEY,
  baked_sha TEXT NOT NULL,            -- the HELIX_BAKED_REPO_SHA the worker booted with
  last_seen TIMESTAMPTZ NOT NULL
)
-- workers UPSERT every 5s. Recovery treats workers with last_seen
-- older than 30s as dead and reclaims their jobs. baked_sha is read
-- by /api/runtime/baked-sha so submit can refuse heterogeneous fleets.

legacy_compile_run_numbers (
  -- Globally unique results/NNNN allocator per (program_version) for
  -- compile jobs. Resolves the concurrent-collision risk: each worker
  -- runs in its own /work/ workdir, so compile.py's max(results)+1
  -- logic would otherwise hand the same number to two concurrent jobs.
  program_version_id INT PRIMARY KEY,
  next_number INT NOT NULL                  -- value the NEXT allocation will return
)

legacy_eval_run_numbers (
  -- Per-compile-job allocator for evals/<NNNN>.
  compile_job_id UUID PRIMARY KEY,
  next_number INT NOT NULL
)

-- Convention: next_number stores the value to be returned on the NEXT
-- allocation (NOT "the next free number plus one"). Initial value =
-- max(observed) + 1, where "observed" is the highest NNNN directory
-- already present in:
--   - compile allocator: <baked-repo>/backend/ai/programs/<p>/<v>/results/
--     (directory names matching ^\d{4}$); fallback 0 → next_number = 1.
--   - eval allocator: <baked-repo>/backend/ai/programs/<p>/<v>/results/<parent.emitted_run_number>/evals/;
--     fallback 0 → next_number = 1.
--
-- Allocation in one round-trip:
--   INSERT INTO legacy_compile_run_numbers (program_version_id, next_number)
--   VALUES ($pvid, <seed_max_plus_1> + 1)
--   ON CONFLICT (program_version_id)
--   DO UPDATE SET next_number = legacy_compile_run_numbers.next_number + 1
--   RETURNING next_number - 1;
-- The RETURNING value is the allocated NNNN. The INSERT branch reserves
-- (max+1) and bumps next_number to (max+2), so a concurrent second
-- inserter gets (max+2) via the UPDATE branch. No off-by-one.
-- Same shape for legacy_eval_run_numbers.

artifacts (
  id UUID PK,
  job_id FK,
  relative_path TEXT NOT NULL,        -- path relative to the job's results-dir root, e.g. 'compile/compiled_program/program.pkl', 'gepa_logs/iter_001/state.json', 'evals/0001/results.jsonl', 'program.hash'. Reconstructable into a full results dir on export.
  kind TEXT,                          -- coarse classification for UI/filtering, derived from relative_path: 'stdout_log' | 'compiled_program' | 'results_jsonl' | 'gepa_log' | 'config' | 'metrics_py' | 'program_py' | 'program_hash' | 'eval_summary_md' | 'other'
  blob_key TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  sha256 CHAR(64) NOT NULL,           -- content hash, used by `helix export` to skip unchanged files
  mime TEXT,
  attempt INT NOT NULL,               -- which job attempt produced this artifact (matches jobs.attempt)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (job_id, attempt, relative_path)
)
```

Lineage queries (e.g. "all evals against compile X", "all compiles on dataset
028 split 001") become trivial joins.

### Execution contract (the single most important section)

This contract is what makes Helix work without forking `compile.py` /
`evaluate.py`. It explicitly addresses both the source-root and the
closed-dependency issues:

1. **All Helix images share one clean repo snapshot at a known commit
   SHA.** `helix up` (and `--rebuild`) refuses to build if the working
   tree has uncommitted changes under baked-only roots (see the
   `BAKED_ROOTS` list below). The build then runs
   `git archive <HEAD-sha> | tar -x -C <build-context>` into a single
   temporary directory, and **both** the worker Dockerfile and the
   api Dockerfile `COPY` from that *same* archive — **never** from the
   live worktree. The build script writes `HELIX_BAKED_REPO_SHA=<sha>`
   into the env of every image (api, worker, even the ui build for
   display). Worker and api therefore always agree on `baked_sha`; the
   `/api/runtime/baked-sha` endpoint reads it from the api container's
   own env. The image's `/repo-snapshot/` is read-only at runtime.
   Each job row stores `baked_sha` for reproducibility.
2. **`compile.py` / `evaluate.py` are NOT copied to `/helix/`** — they
   are invoked from their natural location inside the baked repo
   (`/repo/.claude/skills/ai-utils/compile.py`). This preserves the
   sibling-import resolution they already do (`compile.py:13` derives
   `backend/ai` from its own file location) without any code change.
3. **The job bundle is a path-restricted overlay, not a closure.**
   - **Overlayable root (changes ship in the bundle, no rebuild
     needed):** `backend/ai/programs/` (the full programs tree —
     cross-version dependencies like v06/metrics.py loading v05
     metrics must round-trip), but excluding
     `backend/ai/programs/*/*/results/**` (the legacy host results
     dir, which is irrelevant inside a worker: Helix stores
     artifacts in blob storage, and including a copy would both
     bloat the bundle and corrupt `compile.py`'s next-run-number
     allocation).
   - **Baked-only roots (changes require `helix up --rebuild`):**
     these are the *actual* paths the worker imports from (verified
     against this repo's layout):
     - `.claude/skills/ai-utils/` (compile.py, evaluate.py, tracing.py,
       evaluator, metric loader)
     - `backend/ai/api/` (e.g. `backend/ai/api/generated`,
       `backend/ai/api/utils/my_react`)
     - `backend/ai/runtime/`
     - `backend/ai/deploy/`
     - `backend/ai/scripts/`
     - `backend/ai/pyproject.toml` and `backend/ai/uv.lock` (env spec)
     - `backend/ai/Dockerfile` (only if reused for the worker image
       base — otherwise ignore)
     - `.claude/skills/ai-utils/helix/` itself (api, worker, ui, cli)
     - Any new subtree under `backend/ai/` that is **not**
       `backend/ai/programs/`
   - Submitting a job with dirty files under a baked-only root is a
     **hard error** at submit time. The CLI prints the offending paths
     and instructs the user to `helix up --rebuild` (or stash/revert).
   - **Deletions and renames are not overlay-representable in v1.**
     If a tracked file under an overlayable root has been deleted or
     renamed in the working tree vs `baked_sha`, submit hard-errors
     and asks the user to commit + `helix up --rebuild`. Tombstone
     support is a v2 task.
4. **On job start the worker** mounts the per-job repo at
   `/work/<job-id>/repo/` using **overlayfs** with the baked
   `/repo-snapshot/` as a read-only `lowerdir` and a per-job
   `upperdir` + `workdir` on tmpfs:
   ```
   mount -t overlay overlay \
     -o lowerdir=/repo-snapshot,upperdir=/work/<job-id>/upper,workdir=/work/<job-id>/wd \
     /work/<job-id>/repo
   ```
   The baked snapshot stays immutable across jobs; all writes
   (overlay tarball extraction, compile.py results dirs, evaluate.py
   evals dirs) land in the per-job upperdir. On job cleanup the mount
   is unmounted and the upperdir wiped.
   Fallback if overlayfs is unavailable (e.g. the worker container
   lacks `CAP_SYS_ADMIN`): a plain `cp -R /repo-snapshot
   /work/<job-id>/repo`. Slower (~hundreds of MB to copy) but
   guaranteed safe. Never use `cp -al`: hardlinks would let a writer
   mutate the shared snapshot inode.
   The bundle tar is then extracted on top of `/work/<job-id>/repo/`
   (which writes only into the upperdir). The worker then runs
   `cd /work/<job-id>/repo/backend/ai && python3 /work/<job-id>/repo/.claude/skills/ai-utils/compile.py --config <overlaid path>`.
   The sys.path derivation in compile.py / evaluate.py resolves to the
   correct overlaid tree.
5. **Eval `--compilation`:** worker downloads parent compile job's
   `results/<NNNN>/` artifacts into the overlaid repo at their original
   relative path under `programs/<p>/<v>/results/<NNNN>/`, recreates
   the `data` symlink, then invokes `evaluate.py --compilation
   programs/<p>/<v>/results/<NNNN>`.

### Job bundle (client → server)

#### Overlay capture rules (precise)

`helix submit` queries `GET /api/runtime/baked-sha` to learn the worker
image's repo commit. The path constants:
```
OVERLAY_ROOTS = ['backend/ai/programs/']
BAKED_ROOTS   = [
  '.claude/skills/ai-utils/',          # entry-points + tracing + helix itself
  'backend/ai/api/',                   # backend/ai/api/generated, api/utils/my_react, …
  'backend/ai/runtime/',
  'backend/ai/deploy/',
  'backend/ai/scripts/',
  'backend/ai/pyproject.toml',
  'backend/ai/uv.lock',
  'backend/ai/Dockerfile',
]
# Effectively: anything under backend/ai/ that is NOT
# backend/ai/programs/ is baked-only.
```
A single exclude is applied to every overlay query:
`backend/ai/programs/*/*/results/`.

The bundle is the UNION of:

1. **The user-supplied config file(s).** Configs MUST live under an
   overlayable root (`backend/ai/programs/<p>/<v>/...`) — submit
   hard-errors otherwise. This preserves `compile.py`'s convention of
   resolving `data.splits` relative to the config file's directory.
2. **Tracked changes under overlayable roots:**
   ```
   git diff   --name-status <baked_sha> -- :(top)backend/ai/programs/ :!backend/ai/programs/*/*/results/
   git diff --cached --name-status      -- :(top)backend/ai/programs/ :!backend/ai/programs/*/*/results/
   ```
   Filter:
   - `A|C|M` → include as overlay file.
   - `D` (deletion) or `R*` (rename, in any direction) → **hard
     error**. Per execution-contract item 3, deletions and renames are
     not overlay-representable in v1; the user must commit and
     `helix up --rebuild`.
3. **Untracked files under overlayable roots:**
   ```
   git ls-files --others --exclude-standard -- backend/ai/programs/ ':!backend/ai/programs/*/*/results/'
   ```
4. **Dirty-file check on baked-only roots** (any tracked diff,
   untracked file, deletion, or rename under `BAKED_ROOTS`) → hard
   error with the offending paths printed.

The bundle tar preserves repo-relative paths. Metadata posted:
`{program, version, dataset, split, config_path, baked_sha,
overlay_files: [...]}`.

CLI infers `program`, `version`, `dataset`, `split` from the config YAML
paths + content; user can override with explicit flags.

### Worker execution

`helix-worker/runner.py`:
1. **Claim a job from Postgres** with
   ```sql
   UPDATE jobs
   SET status='running',
       worker_id=$me,
       started_at=COALESCE(started_at, now()),
       lease_expires_at = now() + interval '30 seconds',
       attempt = attempt + 1
   WHERE id = (
     SELECT id FROM jobs
     WHERE status='queued'
     ORDER BY created_at
     FOR UPDATE SKIP LOCKED
     LIMIT 1
   )
   RETURNING *;
   ```
   A background thread on the worker UPSERTs `worker_heartbeats` and
   extends `lease_expires_at` every 5s while the job runs. Postgres is
   the durable queue; redis is *not* on the durability path.
2. Build overlaid repo at `/work/<job-id>/repo/` per the execution
   contract (overlayfs lowerdir=`/repo-snapshot`, per-job upper+wd
   on tmpfs; `cp -R` fallback if overlayfs is unavailable) and
   extract the uploaded bundle tar on top.
3. If eval: download parent compile's `results/<NNNN>/` artifacts into
   the overlay at their original path; recreate the `data` symlink.
4. Set env: `LANGFUSE_*` from worker's docker env (worker container
   sees Langfuse on its compose-internal hostname),
   `KIN_AI_RUN_LABEL=<job-id-short>`, propagate user secrets
   (`OPENAI_API_KEY`, etc.) injected by compose from `.env`.
5. **Allocate `emitted_run_number`**:
   - Compile job → allocate from `legacy_compile_run_numbers` keyed by
     `program_version_id`. Let the allocated number be `N`. Seed the
     overlay by creating empty directories
     `programs/<p>/<v>/results/0001/` through `.../000(N-1)/` (only
     those not already present in the baked snapshot's tracked result
     dirs). `compile.py`'s `max(results)+1` then resolves to `N`
     deterministically.
   - Eval job → allocate from `legacy_eval_run_numbers` keyed by
     `parent_job_id`. After downloading the parent compile's artifacts
     into the overlay (step 3), seed empty placeholder dirs under
     `<results-dir>/evals/0001/ … 000(M-1)/` so `evaluate.py`'s
     `max(evals)+1` resolves to the allocated `M`.
   - Persist as `jobs.emitted_run_number`. **Verification:** after
     the subprocess exits, the worker asserts the actual emitted dir
     matches the allocated number; mismatch fails the job. The blob
     keys for every artifact include `emitted_run_number` in their
     path so blob lookups never have to consult the (mutable)
     `export_run_number`.
6. Spawn the canonical entry-point inside the overlaid repo **in its
   own process group**, so cancel can SIGTERM/SIGKILL the entire group
   (DSPy/litellm can leave subprocess children behind otherwise):
   ```python
   proc = subprocess.Popen(
       ["python3", "/work/<job-id>/repo/.claude/skills/ai-utils/compile.py",
        "--config", "<overlay-relative-config-path>"],
       cwd="/work/<job-id>/repo/backend/ai",
       start_new_session=True,   # new session ⇒ new process group; PGID == proc.pid
   )
   ```
   (or `evaluate.py`). No host bind-mounts; no path patching of the
   scripts themselves.
7. Tee stdout/stderr → redis pub/sub channel `helix:logs:<job-id>`
   (transient, for live SSE) AND to a local file that is uploaded on
   completion (durable, in blob store).

**Fencing rule (applies to every Postgres write the worker performs
after step 1, including artifact INSERTs and the terminal status
UPDATE):** every statement is conditional on the worker still owning
the claim:
```sql
UPDATE jobs SET ... WHERE id=$job_id AND worker_id=$me AND attempt=$attempt;
INSERT INTO artifacts (job_id, attempt, ...)
  SELECT $job_id, $attempt, ...
  WHERE EXISTS (
    SELECT 1 FROM jobs
    WHERE id=$job_id AND worker_id=$me AND attempt=$attempt
  );
```
If the row's `worker_id` or `attempt` has changed (because the lease
expired and another worker claimed the job — see step 10), all of
this worker's late writes silently no-op. The stale process can then
exit harmlessly; its partial blob objects are unreferenced garbage
(prune-able later). This is the standard "fencing token" pattern;
`(worker_id, attempt)` is the token.
8. **Post-run bookkeeping (worker, not compile.py).** `compile.py`
   does NOT produce `program.hash` or the root-level compile-config
   copy on its own — those were generated by the now-deleted
   `launch_compile_eval.py`. The worker is now responsible for them:
   - Compile jobs, before uploading:
     - Compute `program.hash` = `sha256(<results-dir>/compile/compiled_program/program.pkl)`; write to `<results-dir>/program.hash`.
     - Copy the submitted compile-config YAML to `<results-dir>/<config-basename>` (the legacy convention used by `/ai-deploy`).
   - Eval jobs, before uploading: generate `<results-dir>/EVAL_SUMMARY.md` from `evals/<emitted_run_number>/results.jsonl` (date, program, metrics table, per-row feedback) per the layout in `.claude/skills/ai-eval/SKILL.md`.
9. **Artifact upload (each job uploads only what it produced).** For
   every uploaded file, the worker records `(relative_path, blob_key,
   size, sha256, kind, attempt)` so the full tree can be
   reconstructed on export and `helix export` can skip unchanged
   files cheaply.
   - **Compile job** uploads, walked recursively, with paths relative
     to `<results-dir>`:
     - `compile/**` — every file under compile/ (program.py, dataset.jsonl, splits.yaml, compile.config.yaml, compiled_program/program.pkl, compiled_program/metadata.json).
     - `gepa_logs/**` — entire optimizer-state tree (required by success criteria; can be tens of MB).
     - `program.hash` (just-written).
     - `<config-basename>` (the root-level config copy).
     - `stdout_log` — kind-only artifact for the streamed worker log (path: `helix/stdout.log`, synthetic — not part of legacy layout).
   - **Eval job** uploads, paths relative to `<results-dir>`:
     - `evals/<this.emitted_run_number>/**` — full subtree (config copy, metrics.py, program.py, dataset.jsonl, splits.yaml, results.jsonl).
     - `EVAL_SUMMARY.md` (just-written; overwrite-on-export is expected — every eval regenerates it).
     - `stdout_log` (synthetic, as above).
     - **Not uploaded:** anything under `compile/`, `gepa_logs/`, `program.hash`, root config copy — those belong to the parent compile job and are linked via `parent_job_id`.
   Then: parse the final status line for summary metrics, mark
   `succeeded`/`failed`.
10. **Startup recovery / lease expiry:** any worker (or the API on
   boot) periodically runs:
   ```sql
   UPDATE jobs
   SET status='queued', worker_id=NULL, lease_expires_at=NULL
   WHERE status='running'
     AND (lease_expires_at < now()
          OR worker_id NOT IN (
            SELECT worker_id FROM worker_heartbeats
            WHERE last_seen > now() - interval '30 seconds'
          ));
   ```
   This is idempotent: artifacts are uploaded only on clean exit;
   partial blob state from a previous attempt is harmless and
   overwritten. `attempt` distinguishes retries in logs.
11. **Cancel (process-group aware):** a sibling thread subscribes to
    redis channel `helix:cancel:<job-id>`. On message:
    ```python
    pgid = os.getpgid(proc.pid)   # == proc.pid because start_new_session=True
    os.killpg(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(pgid, signal.SIGKILL)
        proc.wait()
    ```
    This catches DSPy/litellm child processes (parallel evaluator
    workers, HTTP keep-alive helpers) that a raw `os.kill(pid,
    SIGKILL)` would orphan. Partial artifacts are then uploaded and
    `status='cancelled'`. Redis here is non-durable: a missed cancel
    just means the job runs to natural completion — recoverable, not
    corrupting.

### CLI

```
helix bootstrap                    # interactive: prompts OPENAI_API_KEY, GEMINI_API_KEY, etc.;
                                   # writes .claude/skills/ai-utils/helix/.env (gitignored)
helix up | down | status           # wraps `docker compose -p kincalendar-helix ...`

helix submit compile <config> [<config> ...] \
       [--auto-eval <eval-config>] [--no-auto-eval] \
       [--program <name>] [--version <v>]
                                   # MULTI-config: each <config> is a separate compile job, sharing one
                                   # bundle upload. Default behaviour: chain an eval after each
                                   # successful compile (mirrors today's auto-chain in feedback memory
                                   # `feedback_compile_auto_eval.md`). --no-auto-eval opts out
                                   # (matches today's --compile-only). --auto-eval <path> overrides
                                   # the convention of `eval.config.<latest>-test.yaml`.
                                   # Prints one {job_id, run_label, ui_url, langfuse_url} per submitted job.

helix submit eval    <eval-config> [<eval-config> ...] \
       --compile-job <uuid> | --compilation <local-results-dir>
                                   # --compile-job: reference a Helix-owned compile by id.
                                   # --compilation: import a legacy local results dir before the eval.
                                   # The CLI runs `helix import-compile <local-results-dir>` first,
                                   # which creates an ad-hoc compile job row with status='succeeded',
                                   # type='compile', program_version_id/dataset_id/split_id inferred
                                   # from compile.config.yaml + splits.yaml in the dir, run_label set
                                   # to "imported_<sha1[:6]>", emitted_run_number = the NNNN parsed
                                   # from the local path, baked_sha = NULL (sentinel for "not produced
                                   # by a Helix worker"). All files under the dir except evals/** and
                                   # any helix/** are uploaded as artifacts with relative_path
                                   # preserved. The eval submission then proceeds with --compile-job
                                   # set to the new row's id. Importing the same path twice returns
                                   # the existing job id (idempotent on (program_version,
                                   # emitted_run_number)).

helix list   [--program X] [--version V] [--dataset D] [--split S] [--status running] [--limit N]
helix status <job-id>
helix logs   <job-id> [-f]
helix cancel <job-id>
helix open   [<job-id>]            # http://127.0.0.1:7000/jobs/<id>
helix traces <job-id>              # opens http://127.0.0.1:7000/api/langfuse/sso?return_to=… (auto-logs into Langfuse and lands on traces filtered by run_label)

helix export <job-id> [--into <path>]
                                   # **Cutover compatibility.** Materializes the legacy results-dir
                                   # shape under backend/ai/programs/<p>/<v>/results/<NNNN>/ on the host.
                                   # NNNN is the job's export_run_number:
                                   #   - Default = emitted_run_number (the dir the worker actually wrote
                                   #     into blob storage).
                                   #   - If the host already has a directory at that NNNN from a non-Helix
                                   #     manual run (or a different job whose export landed first),
                                   #     export allocates a NEW number from legacy_*_run_numbers and
                                   #     writes export_run_number on the job row. emitted_run_number is
                                   #     never mutated; blob keys are still resolved through it.
                                   # Semantics by job type:
                                   #   compile: materializes every artifact row for the job at its
                                   #            recorded relative_path under results/<export_run_number>/.
                                   #            This covers compile/**, gepa_logs/** (required for
                                   #            byte-equivalent reproduction per success criteria),
                                   #            program.hash, and the root compile-config copy. Also
                                   #            creates the data symlink.
                                   #   eval:    walks parent_job_id chain to its compile, exports the
                                   #            compile (allocating its own export_run_number if needed),
                                   #            then materializes the eval job's artifact rows at
                                   #            evals/<eval.export_run_number>/** and writes/refreshes
                                   #            EVAL_SUMMARY.md at the results-dir root. Sibling evals
                                   #            merge cleanly.
                                   # Filter: artifacts with relative_path starting with 'helix/' are
                                   # SYNTHETIC (stdout_log, etc.) and are NEVER materialized into the
                                   # legacy results dir — they are Helix internals, not part of the
                                   # /ai-deploy contract.
                                   # If the target results/<NNNN>/ already exists from a prior export of
                                   # THIS SAME job (export_run_number matches), export is a no-op for
                                   # unchanged files and refreshes changed ones. Idempotent.
```

Skill commands (`/ai-compile`, `/ai-eval`) keep their current invocation
form (including multi-config submission and auto-chained eval). Their
SKILL.md bodies are rewritten to call `helix submit ...` and to direct
users to `http://127.0.0.1:7000`. **`/ai-deploy` stays on the legacy
results-dir contract for v1**, with `helix export` as the bridge; a
follow-up updates it to query the Helix API directly.

### API contract (OpenAPI source of truth)

**The API spec is the source of truth, not the FastAPI handlers.**
Per the project-wide rule (`feedback_openapi_source_of_truth.md`):
edit the YAML first, regenerate types, then write code that depends on
the generated types only.

Layout:
```
.claude/skills/ai-utils/helix/
├── openapi/
│   ├── openapi.yaml                # hand-edited spec — single source of truth
│   └── codegen.sh                  # one script, regenerates everything
├── api/helix_api/generated/        # generated server models (Pydantic + route stubs via fastapi-code-generator or datamodel-code-generator + a thin handlers/ layer that imports them)
├── ui/lib/api/generated/           # generated TS types + fetch client (via openapi-typescript + openapi-fetch, or @hey-api/openapi-ts)
└── cli/helix_cli/generated/        # generated Python client (via openapi-python-client)
```

Rules:
- **No hand-written request/response Pydantic models on the server.**
  FastAPI route handlers import request/response classes from
  `helix_api/generated/` only. If a handler needs a shape that isn't
  in the spec, the spec changes first.
- **No hand-written TS API types in the UI** and **no hand-written
  HTTP calls in the CLI.** Both consume their generated clients.
- `codegen.sh` is run by CI (and by a pre-commit hook) and fails the
  build if regeneration produces a diff (i.e. generated files are
  committed and must match the spec exactly).
- The spec defines every endpoint listed below, plus error shapes
  (`{ code, message, details }`) for 4xx/5xx, the multipart
  bundle-upload requests, the SSE log stream response (declared as
  `text/event-stream` with a referenced event-payload schema), and
  the `tar.gz` artifact-bulk download (declared as
  `application/gzip` with `format: binary`).

### API endpoints (definitive list — every one is in `openapi.yaml`)

- `POST /api/jobs/compile` (multipart: bundle.tar.gz + metadata JSON) → `{job_id, run_label}`
- `POST /api/jobs/eval` (multipart) → `{job_id, run_label}`
- `GET  /api/jobs?program=&status=&limit=`
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/logs?follow=true` (SSE — proxied from redis pub/sub)
- `POST /api/jobs/{id}/cancel`
- `GET  /api/jobs/{id}/artifacts` — list `[{id, relative_path, kind, size_bytes, sha256, attempt, created_at}, …]`. Optional `?kind=…` or `?prefix=evals/` filters.
- `GET  /api/jobs/{id}/artifacts/{artifact_id}` — stream a single artifact by id (stable identifier; no ambiguity when many rows share a kind, e.g. gepa_logs).
- `GET  /api/jobs/{id}/artifacts.tar.gz` — stream the entire artifact set as a tar (with each artifact at its `relative_path`). Used by `helix export` for bulk download. Optional `?prefix=` to scope.
- `GET  /api/jobs/{id}/traces` → `{ url: "/api/langfuse/sso?return_to=/langfuse/project/kincalendar-ai/traces?environment=<run_label>" }`. Returned URL is relative; the browser hits the SSO endpoint which mints a Langfuse session cookie and 302s into the deep-link. Same origin as Helix UI (`127.0.0.1:7000`) so the cookie binds.
- `GET  /api/langfuse/sso?return_to=<path>` — internal SSO trampoline (described in the "Langfuse subpath hosting + auto-SSO" section). Not directly invoked by clients other than the browser following a redirect.
- `GET  /api/runtime/baked-sha` → `{ baked_sha: "<sha>", workers: [{worker_id, baked_sha, last_seen}, …] }`. Returns the SHA from the API's own image env. If any live worker reports a different `baked_sha` (via heartbeat), include them in the response and the CLI hard-errors with the divergence list, instructing the user to `helix up --rebuild` so all workers converge. Job submission also calls this endpoint and refuses to submit when workers diverge.

### UI (Next.js, served at `/`)

Day-one views:
1. **`/`** — job list table. Columns: id (short), type, program/version, dataset/split, status, started, duration, summary metric. Filters: program, status. Auto-refresh every 5s.
2. **`/jobs/[id]`** — detail page. Header (status, lineage), live log tail (SSE), final metrics, links: "Open in Langfuse" (calls `/api/jobs/{id}/traces`), "Download artifacts". Cancel button when running.

### Skill compatibility (cutover)

| Skill / consumer        | v1 strategy |
|-------------------------|-------------|
| `/ai-compile`           | SKILL.md rewritten to call `helix submit compile <config> [<config>…]`; preserves multi-config + auto-eval-chain. |
| `/ai-eval`              | SKILL.md rewritten to call `helix submit eval --compile-job <uuid>`. |
| `/ai-deploy`            | **Unchanged** in v1. Bridged via `helix export <job-id>` which writes `program.hash`, `EVAL_SUMMARY.md`, `compile/`, `evals/`, and the `data` symlink in the exact legacy layout under `backend/ai/programs/<p>/<v>/results/<NNNN>/`. Migration to API-direct deploy is a v2 task. |
| EVAL_SUMMARY generation | Today produced by `/ai-eval` post-step. Move into worker's post-eval finalization so artifacts in blob storage are deploy-ready; `helix export` then just copies them out. |
| Progress monitoring     | Helix UI replaces `progress_viewer.html`. The eval-progress instructions in `.claude/skills/ai-eval/SKILL.md` (status-line table) still apply — they parse the same final-line format; only the source URL changes. |

### Files to modify in the existing repo

- **Delete** `.claude/skills/ai-utils/launch_compile_eval.py`, `progress_viewer.py`, `progress_viewer.html`, `.claude/skills/ai-utils/langfuse/docker-compose.yml`.
- **Update** `.claude/skills/ai-compile/SKILL.md` and `.claude/skills/ai-eval/SKILL.md`: drop progress_viewer / `/tmp` log instructions; reference `helix submit …` and `http://127.0.0.1:7000`.
- **Update** `.claude/skills/ai-deploy/SKILL.md`: add the `helix export <job-id>` prerequisite step at the top of the workflow (no other change to its existing logic).
- **Keep unchanged** `.claude/skills/ai-utils/compile.py`, `evaluate.py`, `tracing.py` — these are baked into the worker image and invoked from their natural location inside the snapshotted repo. The only Helix-side contracts: stdout has a parseable final-status line (already true) and results dir has the existing structure (already true).
- Update root `.gitignore` to exclude `.claude/skills/ai-utils/helix/.env`.

### Codegen + ergonomics notes

- Choose **one** generator per language to minimise drift:
  - Server: `datamodel-code-generator` for Pydantic models, with
    handlers/ written by hand against them.
  - UI: `@hey-api/openapi-ts` (or `openapi-typescript` +
    `openapi-fetch`) → typed fetch client used by every Next.js page.
  - CLI: `openapi-python-client` → typed Python client used by every
    `helix` subcommand.
- The same `openapi.yaml` is also served by the API at
  `GET /api/openapi.yaml` and rendered at `/api/docs` (FastAPI's
  built-in Swagger UI) so the running server's contract is always
  discoverable.

### Acknowledged open risks (flagged by review, accepted for v1)

- **Worker image rebuild on baked-root edits.** Edits under any
  `BAKED_ROOTS` path (`.claude/skills/ai-utils/`, `backend/ai/api/`,
  `backend/ai/runtime/`, `backend/ai/deploy/`, `backend/ai/scripts/`,
  `backend/ai/pyproject.toml`, `backend/ai/uv.lock`,
  `backend/ai/Dockerfile`) require `helix up --rebuild`.
  The CLI hard-errors on submit if those roots are dirty against
  `baked_sha`, so users can't silently ship inconsistent code. The
  active iteration path (`backend/ai/programs/<p>/<v>/`) is fully
  overlay-covered and never needs rebuild.
- **Pinned Langfuse image for subpath hosting.** v1 requires a
  langfuse-web image built with `NEXT_PUBLIC_BASE_PATH=/langfuse`
  (either an upstream tag known to ship with subpath support, or a
  ~10-line local layer that rebuilds with that env). Drift here will
  surface as broken static-asset paths under the subpath.

## Verification

End-to-end test on a single laptop:

1. **Bootstrap:** `helix bootstrap` — fill prompts; confirm `.env` written.
2. **Bring up:** `helix up`; `docker compose ps` shows all services healthy; `curl http://127.0.0.1:7000/api/jobs` returns `[]`; `http://127.0.0.1:7000/langfuse` loads the Langfuse UI through Caddy (no `:3010` is bound on the host). Visiting `http://127.0.0.1:7000/api/langfuse/sso?return_to=/langfuse` lands the user authenticated on Langfuse with no login screen.
3. **Submit a compile** (reuses today's dry-run target):
   ```
   helix submit compile \
     backend/ai/programs/calendar-event-agent/v06/compile.config.0033.yaml
   ```
   Expect: job appears via `helix list`; UI shows it queued → running; log tail streams; the "Open in Langfuse" link routes through `/api/langfuse/sso` and lands on `/langfuse/project/kincalendar-ai/traces?environment=<run_label>` showing this run's DSPy calls.
4. **Cancel:** `helix cancel <id>` mid-run; status flips to `cancelled` within ~1s; `helix status` shows partial artifacts present.
5. **Resubmit + let finish:** verify `program.pkl` artifact is downloadable; `summary` JSON populated.
6. **Submit eval against it:**
   ```
   helix submit eval \
     backend/ai/programs/calendar-event-agent/v06/eval.config.028_001-test.yaml \
     --compile-job <compile-id>
   ```
   Expect: `parent_job_id` set; eval pulls `program.pkl` from compile's artifacts; results.jsonl uploaded; UI shows lineage.
7. **Persistence:** `helix down && helix up`; previous jobs still listed; artifacts still downloadable.
8. **Trace correlation:** click "Open in Langfuse" on a finished job; only that job's traces are visible.
9. **Multi-config + auto-eval-chain:** `helix submit compile cfg-A.yaml cfg-B.yaml` enqueues two compiles; each auto-spawns its eval on success. `helix list` shows four lineage-linked rows.
10. **Deploy compatibility:** `helix export <eval-job-id>` materializes `backend/ai/programs/<p>/<v>/results/<NNNN>/` with `program.hash`, `EVAL_SUMMARY.md`, `compile/`, `evals/<NNNN>/`, and `data` symlink. `/ai-deploy` against that path runs unchanged.
11. **Crash recovery:** with a job `running`, `docker compose kill helix-worker` then `docker compose up -d helix-worker`. Worker boot finds the orphaned row, requeues it, and a fresh attempt completes successfully. Postgres never reports a phantom `running` row after the worker is back.
