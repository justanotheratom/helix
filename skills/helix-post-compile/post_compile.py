"""Build a deployable program pkl from a compiled training-wrapper.

Some training setups compile a *wrapper* module that differs from the module
the consumer's API actually serves (e.g. a single-LM-call training wrapper
that exposes inner predictors). After compilation, the optimized state must
be transplanted into the deploy-shaped module so the consumer's API loader
can pickle-resurrect a serving artifact. This script does that transplant.

Given:
  --results-dir <dir>            compile output (contains compile/compiled_program/program.pkl)
  --deploy-program <path.py>     deploy-time program source
  --deploy-class <ClassName>     class inside that source to instantiate at load time

This script:
  1. Loads the compiled wrapper via Helix's program_loader.
  2. Dumps its full recursive state (dspy.Module.dump_state).
  3. Wraps the deploy program source + state into a SelfContainedProgram.
  4. Writes <results-dir>/merged/compiled_program/{program.pkl, metadata.json}
     and <results-dir>/merged/program.hash (sha256 of the pkl).
  5. Round-trip loads the merged artifact to confirm it deserializes.

Requirements on the deploy class:
  - Subclass of dspy.Module.
  - Same predictor topology as the compile wrapper (matching dump_state /
    load_state shape). Typically the deploy class HAS a `dspy.ReAct` (or
    equivalent composite) whose inner Predict/CoT names match those inside
    the compile-time wrapper.
  - Accepts the same `config_dict` the compile wrapper was built with, or a
    superset that ignores extras.

Run with the CONSUMER'S Python (so `dspy`, `cloudpickle`, and the consumer's
program-version-local modules import). HELIX_HOME must point at the cloned
Helix repo so this script can locate `program_loader` (from helix/runtime/)
and the `helix_config` loader (from helix/common/). The consumer's `base`
dir is read from `.helix.toml` (found by walking up from cwd).

Usage:
  cd <consumer-repo-root>     # must contain .helix.toml
  uv run python "$HELIX_HOME/skills/helix-post-compile/post_compile.py" \
      --results-dir <base>/<overlay-root>/<p>/<v>/results/<NNNN> \
      --deploy-program <base>/<overlay-root>/<p>/<v>/program.py \
      --deploy-class <DeployClassName>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _resolve_helix_home() -> Path:
    env = os.environ.get("HELIX_HOME")
    if env:
        return Path(env).resolve()
    # Fall back: this script lives at <helix_home>/skills/helix-post-compile/.
    return Path(__file__).resolve().parents[2]


def _consumer_root() -> Path:
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    )


def _setup_sys_path() -> str:
    """Put helix/runtime, helix/common, and the consumer's <base> on sys.path
    so program_loader + helix_config import, and the wrapper's sibling
    imports resolve. Returns the consumer base path (for diagnostics)."""
    helix_home = _resolve_helix_home()
    for p in (helix_home / "common", helix_home / "runtime"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    from helix_config import find_config  # noqa: E402 — sys.path was just set

    cfg = find_config(os.getcwd())
    consumer_base = _consumer_root() / cfg.base
    if not consumer_base.is_dir():
        raise FileNotFoundError(
            f"snapshot base dir {consumer_base} does not exist "
            f"(check [snapshot].base in {cfg.source_path})"
        )
    if str(consumer_base) not in sys.path:
        sys.path.insert(0, str(consumer_base))
    return str(consumer_base)


def merge(results_dir: Path, deploy_program: Path, deploy_class: str) -> Path:
    consumer_base = _setup_sys_path()

    from program_loader import load_compiled_program, SelfContainedProgram  # noqa: E402
    import cloudpickle  # noqa: E402

    print(f"Consumer base (on sys.path): {consumer_base}")
    print(f"Loading compiled wrapper from {results_dir}…")
    wrapper = load_compiled_program(results_dir)

    print("Dumping wrapper state (recursive dump_state)…")
    full_state = wrapper.dump_state()

    if not deploy_program.is_file():
        raise FileNotFoundError(f"deploy program source not found: {deploy_program}")
    source = deploy_program.read_text()
    if f"class {deploy_class}" not in source:
        raise ValueError(
            f"deploy program {deploy_program} does not define `class {deploy_class}`"
        )

    # Reuse the same config the wrapper was built with so the deploy module
    # picks up matching LM / module settings (max_iters, etc.). Skip if the
    # wrapper doesn't carry a pydantic config — deploy class must then default.
    config_dict = wrapper.config.model_dump() if hasattr(wrapper, "config") else {}

    deploy_wrapper = SelfContainedProgram(
        source_code=source,
        class_name=deploy_class,
        config_dict=config_dict,
        state=full_state,
    )

    merged_dir = results_dir / "merged"
    out_dir = merged_dir / "compiled_program"
    out_dir.mkdir(parents=True, exist_ok=True)
    pkl_path = out_dir / "program.pkl"
    with pkl_path.open("wb") as f:
        cloudpickle.dump(deploy_wrapper, f)
    metadata = {
        "source": "helix-post-compile/post_compile.py",
        "merged_from": str(results_dir),
        "deploy_program": str(deploy_program),
        "class_name": deploy_class,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    digest = hashlib.sha256(pkl_path.read_bytes()).hexdigest()
    (merged_dir / "program.hash").write_text(digest)
    print(f"Wrote {pkl_path}")
    print(f"Wrote {merged_dir / 'program.hash'} ({digest[:12]}…)")

    print("Round-trip load test…")
    loaded = load_compiled_program(merged_dir)
    if loaded.__class__.__name__ != deploy_class:
        raise AssertionError(
            f"expected {deploy_class}, got {loaded.__class__.__name__}"
        )
    print(f"Round-trip OK: class={loaded.__class__.__name__}")
    return pkl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-dir", required=True, type=Path,
                    help="Compile results dir containing compile/compiled_program/program.pkl")
    ap.add_argument("--deploy-program", required=True, type=Path,
                    help="Path to deploy-time program.py (defines --deploy-class)")
    ap.add_argument("--deploy-class", required=True,
                    help="Name of the deploy class inside --deploy-program")
    args = ap.parse_args()
    merge(args.results_dir.resolve(), args.deploy_program.resolve(), args.deploy_class)


if __name__ == "__main__":
    main()
