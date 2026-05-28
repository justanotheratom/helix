---
name: helix
description: Reference for the Helix CLI — a local DSPy compile/eval job runner shipped as a uv workspace at HELIX_HOME. Use when the user wants to bring the stack up/down, check status, browse jobs, view logs, cancel jobs, open traces, scaffold a consumer config, run housekeeping (gc, doctor), or otherwise drive Helix from the command line. For task-shaped workflows (compile, eval, export), prefer helix-compile / helix-eval / helix-export.
---

# helix — CLI reference

Helix is a self-contained, repo-agnostic local stack that owns the DSPy
compile/eval job lifecycle (durable Postgres queue, content-addressed
snapshots, per-snapshot uv venv, Langfuse traces, blob artifacts). It runs
from a clone — no published image registry.

## One-time setup

```bash
# 1) Clone Helix wherever you like.
git clone https://github.com/justanotheratom/helix ~/GitHub/helix
export HELIX_HOME=~/GitHub/helix

# 2) Define a `helix` shortcut that runs the CLI from the workspace. First
#    invocation will sync the workspace venv from helix/uv.lock (one-time).
helix() { uv run --project "$HELIX_HOME" helix "$@"; }
```

Run all `helix …` commands from your **consumer worktree** — the one with a
`.helix.toml`. The CLI's stack commands (`up`, `down`, `dev …`) operate on
`$HELIX_HOME/deploy/`; `submit`/`status`/etc. operate on the worktree.

## Consumer onboarding

A consumer repo's only Helix artifact is `.helix.toml` at its root. Scaffold
it interactively:

```bash
cd <consumer-repo>
helix init                    # writes a validated .helix.toml
helix bootstrap               # interactive: writes deploy/.env with provider keys
```

`.helix.toml` declares `repo_id`, the snapshot `base` dir, overlay roots, the
consumer `uv.lock` path, and the Langfuse project id.

## Stack lifecycle

```bash
helix up                      # build-if-missing + start everything (caddy on :7000)
helix down                    # stop everything (named volumes — and thus data — kept)
helix status                  # docker compose ps for the stack
helix dev up [--rebuild]      # source-mounted dev mode: api hot-reloads on edit
helix dev restart [services]  # ~1s process restart (default: helix-worker), no rebuild
```

Data (jobs, snapshots, artifacts, traces) lives in named volumes and survives
restarts, image rebuilds, and `down`. Only `docker compose down -v` wipes it.

## Jobs

```bash
helix submit compile <compile-config> [<compile-config> ...] [--no-auto-eval]
helix submit eval    <eval-config>    --compile-job <uuid>
helix submit eval    <eval-config>    --compilation <local-results-dir>

helix list [--program X] [--version Y] [--status S] [--type compile|eval] [--limit N]
helix status <job-id>          # detail for one job
helix logs <job-id> [-f]       # live SSE log tail
helix cancel <job-id>          # SIGTERM the running subprocess (+ SIGKILL after 5s)
helix open [<job-id>]          # open the UI (job detail if id given)
helix traces <job-id>          # open the Helix trace view (Langfuse data, internal)
helix export <eval-job-id>     # materialize legacy <results-dir> layout
```

Compile/eval/export have their own workflow skills (`helix-compile`,
`helix-eval`, `helix-export`) with full step-by-step instructions.

## Snapshots & storage

```bash
helix snapshot publish         # publish HEAD's content-addressed snapshot (idempotent)
helix gc [--grace-hours N]     # DRY RUN: reclaim unreferenced snapshots + orphan bundles
helix gc --apply               # actually delete (default: dry run)
```

## Standalone-readiness

```bash
helix doctor                   # audit: zero consumer coupling in Helix code
```

## Where things live

| URL / path | What |
|---|---|
| `http://127.0.0.1:<host_port>` | Helix UI (job list, detail, trace viewer) |
| `http://127.0.0.1:<host_port>/api/openapi.yaml` | API spec |
| `$HELIX_HOME/deploy/.env` | Provider keys + langfuse seed creds |
| `<consumer-repo>/.helix.toml` | Consumer config (repo_id, base, overlay roots, ports) |

`<host_port>` is `[stack].host_port` in `.helix.toml` (default 7000).
Langfuse is internal-only — its UI is **not** exposed; trace browsing is
inside the Helix UI at `/jobs/<id>/traces`.

## Common pitfalls

- "No .env — run `helix bootstrap` first." → run `helix bootstrap` once
  per Helix install to seed provider keys at `$HELIX_HOME/deploy/.env`.
- `helix submit` fails with a snapshot-surface dirty check → commit edits
  outside the overlay roots (e.g. under `api/`, `runtime/`) so they're
  captured in the published snapshot; uncommitted overlay-root edits are
  fine, they ship in the per-job bundle.
- `helix dev …` only matters if you're editing Helix's own code; consumers
  use `helix up` and `helix submit`.
