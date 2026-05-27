"""`helix init` — scaffold a consumer .helix.toml.

The on-ramp for a standalone Helix: a new consumer repo runs `helix init`,
answers a few prompts, and gets a validated .helix.toml at its root. Helix
itself ships no consumer config; this is the only Helix artifact a consumer
keeps in its tree.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from rich.console import Console

from helix_config import CONFIG_FILENAME, HelixConfigError, parse_config

from .config import repo_root

console = Console()


_TEMPLATE = """\
# Helix consumer config. The only Helix-specific file in this repo.
# See `helix doctor` to check standalone-readiness.
repo_id = "{repo_id}"

[snapshot]
# Base dir (PYTHONPATH root) snapshotted whole, minus `exclude`.
base = "{base}"
exclude = [{exclude}]
# Large data fetched out-of-band + mounted as extra lowerdirs (Phase 3).
out_of_band = []

[overlay]
# Base-relative editable subset; edits ship per-job (no snapshot republish).
roots = [{overlay_roots}]

[env]
manager = "uv"
lockfile = "{lockfile}"

[runtime]
helix_version = ">=0.1,<0.2"
python = "{python}"

[stack]
host_port = {host_port}
langfuse_port = {langfuse_port}
langfuse_minio_port = {langfuse_minio_port}
langfuse_project_id = "{langfuse_project_id}"
"""


def _ask(prompt: str, default: str) -> str:
    if not sys.stdin.isatty():
        return default
    val = input(f"{prompt} [{default}]: ").strip()
    return val or default


def _quote_list(items: list[str]) -> str:
    return ", ".join(f'"{i}"' for i in items)


def cmd_init(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except Exception:
        root = os.getcwd()
    target = Path(root) / CONFIG_FILENAME

    if target.exists() and not args.force:
        console.print(f"[yellow]{target} already exists; pass --force to overwrite.[/yellow]")
        return 1

    raw_name = Path(root).name.lower()
    sanitized = re.sub(r"[^a-z0-9_-]+", "-", raw_name).strip("-_")
    default_repo_id = (sanitized[:64] or "myrepo")
    repo_id = _ask("repo_id (safe key: [a-z0-9_-])", default_repo_id)
    base = _ask("snapshot base dir (PYTHONPATH root)", "src")
    overlay = _ask("overlay roots (comma-separated, base-relative)", "programs")
    lockfile = _ask("env lockfile (repo-relative)", f"{base}/uv.lock")
    langfuse_project = _ask("langfuse project id", f"{repo_id}-ai")

    overlay_roots = [r.strip() for r in overlay.split(",") if r.strip()]
    rendered = _TEMPLATE.format(
        repo_id=repo_id,
        base=base,
        exclude=_quote_list(["**/results/", "**/.venv/", "**/__pycache__/"]),
        overlay_roots=_quote_list(overlay_roots),
        lockfile=lockfile,
        python="3.13",
        host_port=7000,
        langfuse_port=3010,
        langfuse_minio_port=9090,
        langfuse_project_id=langfuse_project,
    )

    # Validate before writing — never emit a config that won't load.
    try:
        import tomllib

        parse_config(tomllib.loads(rendered))
    except (HelixConfigError, Exception) as e:  # noqa: BLE001
        console.print(f"[red]Refusing to write — generated config is invalid:[/red] {e}")
        return 2

    target.write_text(rendered)
    console.print(f"[green]wrote[/green] {target}")
    console.print("Next: `helix bootstrap` (set provider keys), then `helix up`.")
    return 0
