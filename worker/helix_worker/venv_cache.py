"""Content-addressed consumer venv.

The snapshot supplies the consumer's *source* (programs/, api/, runtime/ on
PYTHONPATH). The venv supplies third-party wheels (supabase, PyJWT, the job's
dspy/litellm/langfuse at the consumer's pinned versions) — it is the
authoritative, reproducible job environment.

Fingerprint covers everything that can change the resolved env: python
version, helix runtime version, manager, lockfile digest, pyproject digest,
uv version, platform/arch. A miss on any of these means a rebuild.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile

import structlog

log = structlog.get_logger(__name__)

VENV_CACHE = os.environ.get("HELIX_VENV_CACHE", "/var/lib/helix/venvs")


def _digest_file(path: str) -> str:
    if not os.path.isfile(path):
        return "absent"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _uv_version() -> str:
    try:
        return subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return "no-uv"


def fingerprint(snapshot_root: str, cfg) -> str:
    """Stable hash of everything that determines the resolved environment."""
    lockfile = os.path.join(snapshot_root, _rel_to_base(cfg, cfg.env_lockfile)) if cfg.env_lockfile else None
    pyproject = os.path.join(snapshot_root, _rel_to_base(cfg, _pyproject_for(cfg)))
    parts = [
        f"py={sys.version_info.major}.{sys.version_info.minor}",
        f"helix={cfg.runtime.helix_version}",
        f"mgr={cfg.env_manager}",
        f"lock={_digest_file(lockfile) if lockfile else 'none'}",
        f"proj={_digest_file(pyproject)}",
        f"uv={_uv_version()}",
        f"plat={platform.system()}-{platform.machine()}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _rel_to_base(cfg, repo_rel_path: str | None) -> str:
    """A repo-relative path (<base>/uv.lock) → base-relative (uv.lock)
    so it can be found inside the snapshot root (which IS the base dir)."""
    if not repo_rel_path:
        return ""
    return cfg.strip_base_prefix(repo_rel_path)


def _pyproject_for(cfg) -> str:
    # Conventionally next to the lockfile, else <base>/pyproject.toml.
    if cfg.env_lockfile:
        d = os.path.dirname(cfg.env_lockfile)
        return os.path.join(d, "pyproject.toml")
    return f"{cfg.base}/pyproject.toml"


def ensure_venv(snapshot_root: str, cfg) -> str:
    """Return the path to a ready venv for this snapshot's lockfile.

    Built once via `uv sync --frozen` against the snapshot's lockfile;
    cached by fingerprint. Absent lockfile → dev-mode bare venv + warning.
    """
    fp = fingerprint(snapshot_root, cfg)
    venv = os.path.join(VENV_CACHE, fp)
    if os.path.isfile(os.path.join(venv, "bin", "python")):
        return venv

    os.makedirs(VENV_CACHE, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f".{fp[:12]}-", dir=VENV_CACHE)

    lockfile_rel = _rel_to_base(cfg, cfg.env_lockfile) if cfg.env_lockfile else None
    lockfile_abs = os.path.join(snapshot_root, lockfile_rel) if lockfile_rel else None

    if lockfile_abs and os.path.isfile(lockfile_abs):
        # uv sync into a project venv. The lockfile's project dir == its parent.
        project_dir = os.path.dirname(lockfile_abs)
        env = dict(os.environ, UV_PROJECT_ENVIRONMENT=os.path.join(tmp, "venv"))
        subprocess.run(
            ["uv", "sync", "--frozen", "--no-dev"],
            cwd=project_dir, env=env, check=True,
        )
        built = os.path.join(tmp, "venv")
    else:
        log.warning("venv_no_lockfile", note="dev mode; non-reproducible")
        subprocess.run(["uv", "venv", os.path.join(tmp, "venv")], check=True)
        built = os.path.join(tmp, "venv")

    try:
        os.rename(built, venv)
    except OSError:
        if os.path.isfile(os.path.join(venv, "bin", "python")):
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return venv


def venv_python(venv: str) -> str:
    return os.path.join(venv, "bin", "python")
