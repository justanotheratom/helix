"""Generate JSONL datasets from canonical YAML before Helix submit."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import repo_root


def materialize_compile_datasets(config_rels: list[str]) -> list[str]:
    """Run per-program materialize_dataset.py scripts; return generated paths."""
    root = Path(repo_root())
    generated: set[str] = set()

    for rel in config_rels:
        config_path = root / rel
        script = config_path.parent / "materialize_dataset.py"
        if not script.is_file():
            continue

        subprocess.run(
            [sys.executable, str(script), "--config", rel],
            cwd=root,
            check=True,
        )

        # Include the generated JSONL in the overlay bundle even if gitignored.
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        data = cfg.get("data") or {}
        source_rel = data.get("source")
        if not source_rel:
            continue
        source_path = config_path.parent / source_rel
        if source_path.suffix in (".yaml", ".yml"):
            jsonl_path = source_path.with_suffix(".jsonl")
        else:
            splits_rel = data.get("splits")
            if not splits_rel:
                continue
            splits_path = config_path.parent / splits_rel
            splits = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
            jsonl_name = splits.get("source")
            if not jsonl_name:
                continue
            jsonl_path = splits_path.parent.parent / jsonl_name
        if jsonl_path.is_file():
            generated.add(str(jsonl_path.relative_to(root)))

    return sorted(generated)
