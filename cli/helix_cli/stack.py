"""`helix bootstrap / up / down / status`."""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

from functools import lru_cache

from rich.console import Console
from helix_config import HelixConfig, find_config

from .config import helix_home, repo_root


console = Console()


@lru_cache(maxsize=1)
def _cfg() -> HelixConfig:
    # Consumer config (repo_id/ports/langfuse project) comes from the worktree
    # the command is run in, NOT the Helix install.
    return find_config(repo_root())


def _deploy_dir() -> str:
    return os.path.join(helix_home(), "deploy")


def _env_path() -> str:
    return os.path.join(_deploy_dir(), ".env")


def _env_example_path() -> str:
    return os.path.join(_deploy_dir(), ".env.example")


def _compose_cmd(*extra: str) -> list[str]:
    return [
        "docker", "compose",
        "-p", _cfg().compose_project,
        "-f", os.path.join(_deploy_dir(), "docker-compose.yml"),
        "--env-file", _env_path(),
        *extra,
    ]


def _compose_env() -> dict:
    """Process env for compose interpolation, derived from .helix.toml.

    Compose reads ${VAR} from the process env (which takes precedence over
    --env-file), so the stack's ports + langfuse project come from the
    consumer config without mutating .env."""
    c = _cfg()
    env = dict(os.environ)
    env["HELIX_HOST_PORT"] = str(c.stack.host_port)
    env["LANGFUSE_PORT"] = str(c.stack.langfuse_port)
    env["LANGFUSE_MINIO_PORT"] = str(c.stack.langfuse_minio_port)
    env.setdefault("LANGFUSE_INIT_PROJECT_ID", c.stack.langfuse_project_id)
    return env


def cmd_bootstrap(args: argparse.Namespace) -> int:
    env_p = _env_path()
    if os.path.exists(env_p) and not args.force:
        console.print(f"[yellow]{env_p} already exists; pass --force to overwrite.[/yellow]")
        return 1
    shutil.copy(_env_example_path(), env_p)

    interactive_keys = [
        ("OPENAI_API_KEY", "OpenAI API key (sk-...)"),
        ("GEMINI_API_KEY", "Gemini API key (optional, press enter to skip)"),
        ("ANTHROPIC_API_KEY", "Anthropic API key (optional)"),
        ("OPENROUTER_API_KEY", "OpenRouter API key (optional)"),
    ]
    lines = Path(env_p).read_text().splitlines()
    out: list[str] = []
    answers: dict[str, str] = {}
    for k, prompt in interactive_keys:
        val = getpass.getpass(f"{prompt}: ") if "API_KEY" in k else input(f"{prompt}: ")
        if val:
            answers[k] = val.strip()
    for line in lines:
        if "=" in line and not line.startswith("#"):
            k = line.split("=", 1)[0]
            if k in answers:
                out.append(f"{k}={answers[k]}")
                continue
        out.append(line)
    Path(env_p).write_text("\n".join(out) + "\n")
    console.print(f"[green]wrote[/green] {env_p}")
    console.print("Next: `helix up`")
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    if not os.path.exists(_env_path()):
        console.print("[red]No .env — run `helix bootstrap` first.[/red]")
        return 1

    # Snapshot + build.
    if args.rebuild or not _images_exist():
        rc = subprocess.run(
            [os.path.join(_deploy_dir(), "build.sh")],
        ).returncode
        if rc != 0:
            return rc
        subprocess.run(_compose_cmd("build"), check=True, env=_compose_env())

    subprocess.run(_compose_cmd("up", "-d"), check=True, env=_compose_env())
    console.print(f"[green]helix is up[/green] → http://127.0.0.1:{_cfg().stack.host_port}")
    return 0


def cmd_dev_up(args: argparse.Namespace) -> int:
    """Helix-repo dev path: always (re)build the generic images from the local
    helix/ tree, then bring the stack up. (`helix up` pulls prebuilt images
    once a registry exists — Phase 3; today it builds-if-missing.)"""
    args.rebuild = True
    return cmd_up(args)


def cmd_gc(args: argparse.Namespace) -> int:
    """Reclaim storage: drop unreferenced snapshot manifests + their blobs and
    orphan overlay bundles older than --grace-hours. Dry-run unless --apply."""
    from . import api

    dry_run = not args.apply
    rep = api.gc(grace_hours=args.grace_hours, dry_run=dry_run)
    mode = "[yellow]DRY RUN[/yellow]" if rep["dry_run"] else "[red]APPLIED[/red]"
    console.print(
        f"{mode}  manifests={rep['deleted_manifests']}  "
        f"snapshot_blobs={rep['deleted_snapshot_blobs']}  "
        f"orphan_bundles={rep['deleted_orphan_bundles']}  "
        f"(grace={rep['grace_hours']}h)"
    )
    for k in rep.get("snapshot_blob_keys", [])[:20]:
        console.print(f"    snapshot {k}")
    for k in rep.get("bundle_keys", [])[:20]:
        console.print(f"    bundle   {k}")
    if dry_run and (rep["deleted_snapshot_blobs"] or rep["deleted_orphan_bundles"]):
        console.print("Re-run with [bold]--apply[/bold] to delete.")
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    subprocess.run(_compose_cmd("down"), check=True, env=_compose_env())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    subprocess.run(_compose_cmd("ps"), env=_compose_env())
    return 0


def _images_exist() -> bool:
    """Quick heuristic: have we built the helix-api image at least once?"""
    try:
        out = subprocess.run(
            ["docker", "image", "ls", "--format", "{{.Repository}}"],
            check=True, capture_output=True, text=True,
        )
        return f"{_cfg().compose_project}-helix-api" in out.stdout
    except Exception:
        return False
