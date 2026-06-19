"""CLI-side config: Helix base URL, the consumer repo root, and HELIX_HOME.

Two distinct roots once Helix is a standalone repo:
- repo_root(): the CONSUMER worktree (has .helix.toml). Used by submit/snapshot.
- helix_home(): where the Helix source + deploy/ live (this clone). Used by
  the stack commands (up/down/build) and the doctor audit.
In the legacy monorepo layout (consumer/helix/...) both still resolve.
"""
from __future__ import annotations

import getpass
import os
import subprocess
from functools import cache
from pathlib import Path


def _main_worktree_root() -> Path | None:
    """The MAIN working tree's root (not a linked worktree's).

    Secrets/config (HELIX_BASE_URL, CF_ACCESS_* …) are kept in the consumer's
    root `.env`, which lives in the primary checkout — git worktrees don't carry
    their own copy. `--git-common-dir` always points at the shared `<main>/.git`
    regardless of which worktree we're invoked from, so its parent is the main
    root. Best-effort: returns None outside a git repo.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return None
    if not out:
        return None
    common = Path(out)
    if not common.is_absolute():
        common = Path.cwd() / common
    common = common.resolve()
    return common.parent if common.name == ".git" else None


def _load_dotenv(path: Path) -> None:
    """Minimal `.env` loader (KEY=VALUE lines). Does NOT override variables
    already set in the real environment, so an explicit `export` always wins.
    Silent and best-effort — never crashes the CLI."""
    try:
        text = path.read_text()
    except Exception:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _bootstrap_env() -> None:
    """Load the consumer's main-worktree-root `.env` into the environment so the
    CLI picks up HELIX_BASE_URL / CF_ACCESS_* without a manual `source`."""
    root = _main_worktree_root()
    if root is not None:
        _load_dotenv(root / ".env")


_bootstrap_env()  # must run before HELIX_BASE_URL is read below

HELIX_BASE_URL = os.environ.get("HELIX_BASE_URL", "http://127.0.0.1:7000")
HELIX_API_BASE = f"{HELIX_BASE_URL}/api"


def job_ui_url(job_id: str) -> str:
    """Canonical job UI link for this CLI session (uses HELIX_BASE_URL)."""
    return f"{HELIX_BASE_URL.rstrip('/')}/jobs/{job_id}"


def job_traces_url(job_id: str) -> str:
    """Canonical trace viewer link for this CLI session."""
    return f"{HELIX_BASE_URL.rstrip('/')}/jobs/{job_id}/traces"


def access_headers() -> dict[str, str]:
    """Cloudflare Access service-token headers, for talking to a Helix that
    sits behind Cloudflare Access (a remote/team deployment). Set both
    CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET in the environment; when
    unset (the local case) this returns {} and nothing changes."""
    cid = os.environ.get("CF_ACCESS_CLIENT_ID")
    secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if cid and secret:
        return {"CF-Access-Client-Id": cid, "CF-Access-Client-Secret": secret}
    return {}


def user_id() -> str:
    """Stable queue-serialization identity for CLI submissions."""
    explicit = os.environ.get("HELIX_USER_ID")
    if explicit and explicit.strip():
        return explicit.strip()
    explicit = os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()
    return (explicit or "anonymous").strip() or "anonymous"


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
