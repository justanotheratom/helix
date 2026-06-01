---
name: helix-export
description: Materialize a finished Helix job's artifacts into the legacy on-disk results-dir layout via `helix export`. Use when the user wants to export a compile/eval job for a downstream deploy step that reads files from disk, recover artifacts locally, or produce the classic `programs/<p>/<v>/results/<NNNN>/` tree from a Helix job id.
---

# helix-export

Materialize a finished Helix job's artifacts (compile/, gepa_logs/, evals/,
EVAL_SUMMARY.md, program.hash, data symlink) into the legacy on-disk
`results/<NNNN>/` layout — the shape downstream deploy/inspection scripts
usually expect.

## Preflight

This skill assumes Helix is already installed. If `$HELIX_HOME` isn't
set or the Helix repo isn't cloned, **run the `helix-setup` skill first**
— it's idempotent. `helix export` reads job metadata and downloads artifacts
through the Helix API, so the **API must be reachable** — either the local
stack is up (`helix status`) or a remote `HELIX_BASE_URL` is configured. The
job whose artifacts you're materializing must also have completed. (If you
stopped the stack after an eval, bring it back up before exporting — a chained
`/be-ai-deploy` will otherwise fail at the export step.)

All `helix …` commands below run from the **consumer worktree** (the dir
whose `.helix.toml` you want results written under), invoked as:

```bash
uv run --project "$HELIX_HOME" helix <command> [args...]
```

## Usage

```
/helix-export <eval-job-id>
```

Use `<eval-job-id>` (the eval, **not** the parent compile). `helix export`
walks the `parent_job_id` chain so both the compile and the eval land in
the same `results/<export_run_number>/`.

## What to run

```bash
helix export <eval-job-id>
# writes <base>/<overlay-root>/<program>/<version>/results/<NNNN>/
#   compiled_program/        (the trained program as compiled — eval artifact)
#   deploy/compiled_program/  (post_compile=transplant serving artifact; absent for identity)
#   compile/                 (inputs/provenance: program.py, dataset.jsonl, splits.yaml, …)
#   gepa_logs/
#   evals/<NNNN>/
#   compile.config.<NNNN>.yaml + the stable alias compile.config.yaml
#   EVAL_SUMMARY.md
#   program.hash
#   data -> ../../data   (the splits symlink evaluate.py uses)
```

The output path is allocated server-side (Helix prevents collisions with
existing results dirs) and printed at the end. Quote that path back to the
user — downstream skills/scripts will need it.

## Common follow-ups

- **Deploy step** (consumer-specific): copy the **serving** artifact into the
  consumer's serving path. That's `compiled_program/` when the compile config
  used `post_compile.mode=identity`, or `deploy/compiled_program/` (+
  `deploy/program.hash`) when it used `mode=transplant`. The state-transplant
  itself runs in compile.py; the destination is the consumer's deploy concern.
- **Inspect on disk**: open `results/<NNNN>/EVAL_SUMMARY.md` for the
  headline metrics, `compile/compile.config.yaml` for the exact compile
  inputs, and `evals/<NNNN>/results.jsonl` for per-row eval rows.
- **Re-evaluate an old export**: `helix submit eval <eval-cfg>
  --compilation <base>/.../results/<NNNN>` imports the legacy dir as a
  succeeded compile job (idempotent) and runs the eval against it. See the
  `helix-eval` skill.

## Caveat: program-version-local imports

`program.pkl` bundles the source of `program.py` as it was at compile time
(via `SelfContainedProgram.source_code`). That source resolves any
program-version-local sibling imports against the **current on-disk
directory** at load time, not against the pickle. If a sibling module that
existed at compile time has since been deleted or renamed in the working
tree, loading fails with `FileNotFoundError` even though the pkl is intact.

Symptom (from `evaluate.py` or a deploy load):

```
Error loading compiled program: [Errno 2] No such file or directory:
'.../programs/<name>/<version>/<some_module>.py'
```

Fix: temporarily restore the missing file from git, run the load, then
remove it again. Fresh compiles against the current source don't need this
— they bundle whatever's on disk at compile time.
