"""Infer (program, version, dataset, split) from a config YAML path + content."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from helix_config import HelixConfig, find_config


# `data/splits/<dataset>_<split>.yaml` is a FIXED Helix convention (per plan),
# so this pattern is not consumer-configurable.
SPLITS_RE = re.compile(r"data/splits/(\d+)_(\d+)\.ya?ml$")


@lru_cache(maxsize=1)
def _cfg() -> HelixConfig:
    return find_config(os.getcwd())


def infer_program_version(config_path: str) -> tuple[str | None, str | None]:
    # program-version regex is derived from .helix.toml (base + overlay roots).
    m = _cfg().program_version_re().search(config_path)
    if m:
        return m.group(1), m.group(2)
    return None, None


def infer_dataset_split(repo_root: str, config_path: str) -> tuple[str | None, str | None]:
    abs_p = os.path.join(repo_root, config_path)
    if not os.path.isfile(abs_p):
        return None, None
    try:
        doc = yaml.safe_load(Path(abs_p).read_text())
    except Exception:
        return None, None
    if not isinstance(doc, dict):
        return None, None
    data = doc.get("data") or {}
    splits_path = data.get("splits")
    if not isinstance(splits_path, str):
        return None, None
    m = SPLITS_RE.search(splits_path)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def infer_all(repo_root: str, config_path: str) -> tuple[str, str, str, str]:
    program, version = infer_program_version(config_path)
    dataset, split = infer_dataset_split(repo_root, config_path)
    if not (program and version and dataset and split):
        missing = [
            n for n, v in (("program", program), ("version", version), ("dataset", dataset), ("split", split)) if not v
        ]
        raise SystemExit(f"Could not infer {missing} from {config_path}; pass --program/--version explicitly.")
    return program, version, dataset, split
