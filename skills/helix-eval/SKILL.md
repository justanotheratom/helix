---
name: helix-eval
description: Submit a held-out evaluation against an existing compile via the Helix CLI, paste back the job URLs, and surface trace + summary metrics. Use when the user wants to eval a compiled DSPy program, run `helix submit eval`, score a compile on a test split, or re-evaluate a legacy on-disk results dir.
---

# helix-eval

Run a held-out evaluation against an existing compile via the `helix` CLI.
Helix queues the eval, materializes the parent compile's artifacts on the
worker, runs `evaluate.py` against the eval config, and streams progress +
final metrics into the Helix UI.

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
/helix-eval <eval-config> --compile-job <uuid>
```

`<eval-config>` is a path under
`<base>/<overlay-root>/<program>/<version>/eval.config.<dataset>_<split>-test.yaml`,
where `<base>` and `<overlay-root>` come from `.helix.toml`. `<uuid>` is
the Helix compile-job id produced by `helix submit compile` /
`helix-compile`.

## What to run

```bash
helix submit eval <base>/<overlay-root>/<p>/<v>/eval.config.<dataset>_<split>-test.yaml \
                  --compile-job <compile-job-id>
```

The CLI prints `{job_id, run_label, ui_url, traces_url}`. Paste both URLs
into chat.

- Helix downloads the parent compile's `program.pkl` and reseeds the `data`
  symlink convention inside the worker overlay — the consumer's
  `evaluate.py` runs unchanged.
- `EVAL_SUMMARY.md` is generated server-side by the worker and uploaded
  as an artifact (`kind=eval_summary_md`).
- The eval row carries `parent_job_id=<compile-job-id>` so lineage is
  queryable in the UI and via `helix list --type eval`.

## Re-evaluating a legacy local results dir

If you only have a legacy `<base>/<overlay-root>/<program>/<version>/results/<NNNN>/`
on disk (no Helix compile job to reference), submit with `--compilation`:

```bash
helix submit eval <eval-config> \
  --compilation <base>/<overlay-root>/<p>/<v>/results/<NNNN>
```

The CLI runs `helix import-compile` first to materialize that legacy dir
as a `succeeded` compile job (idempotent on `(program_version,
emitted_run_number)`), then submits the eval against the imported id.

## Live progress

The Helix UI's job-detail page shows a live SSE log tail and a parsed
progress panel (rows done/total, accuracy, cost, ETA — derived from the
worker's status line):

```
[N/total] Acc: X% | Tokens: T (in:I/out:O) | Cost: $C | Latency: avg=Ams med=Mms var=Vms² | ETA: Em
```

For a multi-run summary table, use `helix list --type eval`; each job's
`summary` JSON contains `acc_pct`, `cost_usd`, `rows`.

## Trace inspection

`traces_url` opens the Helix-native trace viewer at
`${HELIX_BASE_URL}/jobs/<job-id>/traces` — filtered list of traces for
this eval, click through for the observation tree + per-call input/output.
Langfuse data, no separate login. The viewer is built into Helix; Langfuse
itself is not externally accessible.

## Continuing to deploy

`helix export <eval-job-id>` materializes a legacy results layout (evals/
+ EVAL_SUMMARY.md inside the parent compile's exported `results/<NNNN>/`).
See the `helix-export` skill.
