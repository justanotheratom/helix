---
name: helix-compile
description: Submit a DSPy compile job (with optional auto-chained eval) via the Helix CLI, paste the resulting URLs back to the user, and surface live progress + trace links. Use when the user wants to compile or optimize a DSPy program (typically with GEPA), kick off `helix submit compile`, run a new optimization, or improve a program version.
---

# helix-compile

Submit a DSPy compile job to a running Helix stack via the `helix` CLI.
Helix queues it, publishes a content-addressed snapshot of the consumer's
source, materializes the per-snapshot uv venv on the worker, and streams
GEPA progress live in the Helix UI. An eval is auto-chained on success.

## Preflight

This skill assumes Helix is already installed and the stack is up. If any
of these are missing, **run the `helix-setup` skill first** — it's idempotent:

- `$HELIX_HOME` set and the Helix repo cloned there.
- `.helix.toml` present in the consumer worktree.
- `$HELIX_HOME/deploy/.env` written (provider keys).
- The stack running (`uv run --project $HELIX_HOME helix status` shows
  every helix-* container `Up`).

All `helix …` commands below run from the **consumer worktree** (the dir
whose `.helix.toml` you want to run against), invoked as:

```bash
uv run --project "$HELIX_HOME" helix <command> [args...]
```

## Usage

```
/helix-compile <compile-config> [<compile-config> ...]
```

Each `<compile-config>` is a path under
`<base>/<overlay-root>/<program>/<version>/compile.config.<NNNN>.yaml`,
where `<base>` and `<overlay-root>` come from `.helix.toml`. Multi-config
submission is supported and each job spawns its own auto-eval.

## Prerequisites

The stack must be up:

```bash
helix status        # first-time setup: `helix init && helix bootstrap && helix up`
```

If `helix status` shows services aren't running, start the stack first.

## What to run

```bash
helix submit compile <base>/<overlay-root>/<program>/<version>/compile.config.<NNNN>.yaml
```

The CLI prints `{job_id, run_label, ui_url, traces_url}` for each submitted
job. **Always paste both URLs into chat** so the user can follow along.

- **Auto-eval chaining** is on by default. Helix looks for
  `eval.config.<dataset>_<split>-test.yaml` next to the compile config and
  queues an eval against the compile on success. Override with
  `--auto-eval <path>` or disable with `--no-auto-eval`.
- **Multi-config submission**: `helix submit compile cfg-A.yaml cfg-B.yaml`
  enqueues two independent compiles in one round-trip.
- **Trace viewer is internal** — `traces_url` opens the Helix-native viewer
  at `${HELIX_BASE_URL}/jobs/<job-id>/traces` (proxies Langfuse). No
  separate login.

## Investigating issues

| Symptom | Tool |
|---|---|
| Live log tail | `helix logs <job-id> -f` or the UI's log panel |
| LLM trace inspection | `traces_url` → Helix trace view (rollouts, observations, in/out JSON) |
| Run history | `helix list --program <p> --version <v>` |
| Cancel a runaway | `helix cancel <job-id>` (SIGTERM, then SIGKILL after 5s; data preserved) |
| Submit refused (dirty surface) | Commit changes under `<base>` outside the overlay roots, then resubmit |

## Continuing to deploy

`helix export <eval-job-id>` materializes a legacy `results/<NNNN>/` layout
(compile/, gepa_logs/, evals/<NNNN>/, EVAL_SUMMARY.md, program.hash, data
symlink). Useful when a downstream deploy step expects on-disk artifacts.
See the `helix-export` skill.
