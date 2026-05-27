"""`helix doctor` — standalone-readiness audit.

Verifies the Helix code tree has zero coupling to *this* consumer, so a
`git subtree split` of helix/ would yield a clean, standalone repo. The
"consumer literals" to flag are derived from the loaded config (the base
dir + repo_id) — nothing consumer-specific is hardcoded in the audit itself.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from rich.console import Console

from helix_config import HelixConfigError, find_config

from .config import helix_home, repo_root

console = Console()

# Helix infra + runtime code dirs that must stay consumer-agnostic.
_CODE_DIRS = ("cli", "api", "worker", "common", "runtime")
# Generated client trees legitimately echo schema field examples.
_SKIP_DIR_NAMES = {"generated", "__pycache__", "node_modules", ".next"}


def _scan(helix_root: Path, needles: list[str]) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    pattern = re.compile("|".join(re.escape(n) for n in needles if n))
    for d in _CODE_DIRS:
        base = helix_root / d
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append((str(path), i, line.strip()))
    return hits


def _resolve_helix_root() -> Path:
    """Helix code root. Standalone: helix_home() has the code dirs at its top
    level. Legacy monorepo: they live under <home>/helix/."""
    home = Path(helix_home())
    if (home / "cli").is_dir():
        return home
    if (home / "helix" / "cli").is_dir():
        return home / "helix"
    return home


def cmd_doctor(args: argparse.Namespace) -> int:
    helix_root = _resolve_helix_root()
    if not (helix_root / "cli").is_dir():
        console.print(f"[red]no Helix code dirs under {helix_root}[/red]")
        return 2

    ok = True

    # Consumer config (run from a consumer worktree). Optional: a bare Helix
    # repo has no consumer config, so we can't derive coupling needles —
    # report that rather than failing.
    cfg = None
    try:
        cfg = find_config(os.getcwd())
        console.print(f"[green]✓[/green] .helix.toml loads (repo_id={cfg.repo_id}, base={cfg.base})")
    except HelixConfigError:
        console.print(
            "[yellow]–[/yellow] no consumer .helix.toml in cwd; "
            "run `helix doctor` from a consumer worktree to audit coupling."
        )

    if cfg is not None:
        # Coupling gate — derive needles from the config, so the check itself
        # holds no consumer literal.
        needles = [cfg.base, cfg.repo_id]
        hits = _scan(helix_root, needles)
        if hits:
            ok = False
            console.print(
                f"[red]✗[/red] {len(hits)} consumer-literal hit(s) "
                f"({', '.join(needles)}) in Helix code:"
            )
            for f, ln, text in hits[:50]:
                console.print(f"    {os.path.relpath(f, helix_root)}:{ln}: {text}")
        else:
            console.print(
                f"[green]✓[/green] no consumer literals ({', '.join(needles)}) "
                f"in {{{','.join(_CODE_DIRS)}}}"
            )

        # out_of_band roots exist (if declared) — resolved against the consumer.
        consumer = Path(repo_root()) if _in_git() else Path(os.getcwd())
        for ob in cfg.out_of_band:
            p = consumer / cfg.base / ob
            if p.exists():
                console.print(f"[green]✓[/green] out_of_band root present: {cfg.base}/{ob}")
            else:
                ok = False
                console.print(f"[red]✗[/red] out_of_band root missing: {cfg.base}/{ob}")

    if ok:
        console.print("\n[bold green]OK[/bold green] — Helix code is consumer-agnostic.")
        return 0
    console.print("\n[bold red]coupling found[/bold red] — fix the above.")
    return 1


def _in_git() -> bool:
    try:
        repo_root()
        return True
    except Exception:
        return False
