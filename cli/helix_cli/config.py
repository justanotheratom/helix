"""CLI-side config: Helix base URL, the consumer repo root, and HELIX_HOME.

Two distinct roots once Helix is a standalone repo:
- repo_root(): the CONSUMER worktree (has .helix.toml). Used by submit/snapshot.
- helix_home(): where the Helix source + deploy/ live (this clone). Used by
  the stack commands (up/down/build) and the doctor audit.
In the legacy monorepo layout (consumer/helix/...) both still resolve.
"""
from __future__ import annotations

import os
import subprocess
from functools import cache
from pathlib import Path


HELIX_BASE_URL = os.environ.get("HELIX_BASE_URL", "http://127.0.0.1:7000")
HELIX_API_BASE = f"{HELIX_BASE_URL}/api"


@cache
def repo_root() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


@cache
def helix_home() -> str:
    """Root of the Helix install (the clone). Override with HELIX_HOME, else
    derive from this file's location (cli/helix_cli/config.py → repo root)."""
    env = os.environ.get("HELIX_HOME")
    if env:
        return str(Path(env).resolve())
    return str(Path(__file__).resolve().parents[2])
