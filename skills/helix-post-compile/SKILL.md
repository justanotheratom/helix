---
name: helix-post-compile
description: Transplant the optimized state of a compiled DSPy *training-wrapper* module into a different *deploy-shaped* module class (matching predictor topology) and emit a merged compiled-program artifact under `<results-dir>/merged/`. Use when the user has trained one DSPy class but serves a different class with the same predictor structure, mentions "post-compile", "state transplant", "wrapper vs deploy", "dump_state / load_state", or `<results-dir>/merged/` artifacts. Run from the consumer worktree, with the consumer's Python venv (needs dspy + the consumer's program-version-local modules).
---

# helix-post-compile

A small utility for the common DSPy pattern where training and serving use
**different module classes** that share predictor topology:

- **training wrapper** — exposes a single-LM-call view of the program so
  GEPA / BootstrapFewShot can score it; this is what `helix submit compile`
  produces (`<results-dir>/compile/compiled_program/program.pkl`).
- **deploy class** — the multi-step composite the consumer's API actually
  serves at request time.

`post_compile.py` loads the trained wrapper, `dspy.Module.dump_state`s it,
instantiates the deploy class, `load_state`s the dumped state into it,
re-pickles as a `SelfContainedProgram`, and round-trip-loads to confirm.
The merged artifact lands at:

```
<results-dir>/merged/
├── compiled_program/
│   ├── program.pkl
│   └── metadata.json
└── program.hash
```

Downstream deploy tooling (e.g. kincalendar's `be-ai-deploy`) auto-detects
`<results-dir>/merged/` and prefers it over `<results-dir>/compile/`.

## Preflight

- Helix is installed (`$HELIX_HOME` set, the repo cloned there). If not,
  run the `helix-setup` skill first.
- `.helix.toml` exists in the consumer worktree. The script reads
  `[snapshot].base` to put the consumer's source on `sys.path` so the
  pickled wrapper's sibling imports resolve.
- The compile artifact is on disk at `<results-dir>/compile/compiled_program/program.pkl`.
  If you only have a Helix eval-job UUID, materialize first via
  `helix export <eval-job-id>` (the `helix-export` skill).

## Why "consumer Python", not the Helix workspace venv

This script imports `dspy`, `cloudpickle`, **and** the consumer's deploy
program (a `dspy.Module` subclass with consumer-specific dependencies).
Those live in the consumer's `uv.lock` / venv, not in the Helix workspace
venv. So the invocation is **not** `uv run --project $HELIX_HOME …`; it's
`uv run python …` from the consumer worktree, which uses the consumer's
Python environment.

## What to run

```bash
cd <consumer-repo-root>     # must contain .helix.toml
uv run python "$HELIX_HOME/skills/helix-post-compile/post_compile.py" \
    --results-dir <base>/<overlay-root>/<p>/<v>/results/<NNNN> \
    --deploy-program <base>/<overlay-root>/<p>/<v>/program.py \
    --deploy-class <DeployClassName>
```

Replace `<base>` and `<overlay-root>` with the values from your
`.helix.toml`. `<DeployClassName>` is whatever class inside
`<deploy-program>` you want to serve.

## Requirements on the deploy class

- Must subclass `dspy.Module`.
- Predictor topology must match the trained wrapper's (matching
  `dump_state` / `load_state` shape — i.e. the same set of inner
  `Predict` / `ChainOfThought` / `ReAct` names in the same nesting).
  Typically the deploy class has a `dspy.ReAct` (or equivalent composite)
  whose inner predictors share names with the compile-time wrapper.
- The deploy class's `__init__` must accept the same `config_dict` the
  compile wrapper was built with — or a superset that ignores extras.

## What the script writes

```
<results-dir>/
└── merged/
    ├── compiled_program/
    │   ├── program.pkl        # the deploy class, with transplanted state
    │   └── metadata.json      # provenance: source, merged_from, deploy_program, class_name
    └── program.hash           # sha256 of program.pkl
```

The round-trip load at the end of the script confirms the merged pkl
deserializes as the requested deploy class.

## Failure modes

- `expected <DeployClassName>, got <X>` — predictor topology mismatch
  (`load_state` succeeded on the wrong class, or class names drifted).
- `ModuleNotFoundError` / `ImportError` while loading the wrapper —
  the wrapper's sibling imports can't be resolved. Check that
  `.helix.toml`'s `[snapshot].base` matches your source layout and that
  the missing module is on disk under `<base>/.../`.
- `deploy program <path> does not define class <DeployClassName>` —
  exactly what it says; check the class name + the program path.
