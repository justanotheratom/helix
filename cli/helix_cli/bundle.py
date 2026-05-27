"""Compute the overlay bundle per the plan's "Overlay capture rules".

All roots are derived from `.helix.toml` via HelixConfig — no consumer
path literal lives here.

- OVERLAY roots  = cfg.programs_roots_repo_rel (the program-version dirs),
  excluding <overlay>/<p>/<v>/results/.
- BAKED surface  = everything under cfg.base that is NOT an overlay root,
  plus helix/ itself (Phase 1 keeps baking; editing these needs
  `helix up --rebuild`).

Hard errors:
- Dirty file in the baked surface.
- Deletion or rename under any overlay root (D|R*).
- Config path outside an overlay root.
"""
from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from functools import lru_cache
from pathlib import Path

from helix_config import HelixConfig, find_config

from .config import repo_root


@lru_cache(maxsize=1)
def cfg() -> HelixConfig:
    return find_config(repo_root())


def _overlay_roots() -> tuple[str, ...]:
    # trailing slash form for prefix checks
    return tuple(r + "/" for r in cfg().programs_roots_repo_rel)


def _git(*args: str, cwd: str | None = None) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd or repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def _name_status(baked_sha: str, pathspecs: list[str]) -> list[tuple[str, str, str | None]]:
    """Return [(status, path, rename_source_or_None)] for the given git pathspecs."""
    out: list[tuple[str, str, str | None]] = []
    for src in (["diff", "--name-status", baked_sha, "--", *pathspecs],
                ["diff", "--cached", "--name-status", baked_sha, "--", *pathspecs]):
        text = _git(*src)
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            if status.startswith("R"):
                out.append((status, parts[2], parts[1]))
            else:
                out.append((status, parts[1], None))
    return out


def _untracked(pathspecs: list[str]) -> list[str]:
    out = _git("ls-files", "--others", "--exclude-standard", "--", *pathspecs)
    return [p for p in out.splitlines() if p.strip()]


def _under_root(path: str, root: str) -> bool:
    if root.endswith("/"):
        return path.startswith(root) or path == root.rstrip("/")
    return path == root or path.startswith(root + "/")


def _is_results_path(path: str) -> bool:
    """A path is a results artifact iff it is <overlay_root>/<p>/<v>/results/..."""
    for r in cfg().programs_roots_repo_rel:
        prefix = r + "/"
        if path.startswith(prefix):
            rest = path[len(prefix):].split("/")
            if len(rest) >= 3 and rest[2] == "results":
                return True
    return False


def head_sha() -> str:
    return _git("rev-parse", "HEAD").strip()


def _snapshot_surface_pathspecs() -> list[str]:
    """The snapshot surface = base dir minus overlay roots.

    Editing it requires republishing the snapshot (it's built from HEAD), so
    uncommitted changes here would silently run stale code. `helix/` is NOT
    part of the snapshot (it lives in the generic image), so it's excluded.
    """
    c = cfg()
    specs = [c.base]
    for r in c.programs_roots_repo_rel:
        specs.append(f":(exclude){r}")
    return specs


def check_snapshot_surface_clean(base_sha: str) -> None:
    """Hard-error if the snapshot surface has uncommitted changes.

    The snapshot is built from `base_sha` (HEAD); changes outside the overlay
    roots that aren't committed won't be in it, so the job would run stale
    source. Overlay-root edits are fine — they ship in the per-job bundle.
    """
    dirty: list[str] = []
    specs = _snapshot_surface_pathspecs()
    for status, path, _ in _name_status(base_sha, specs):
        if path:
            dirty.append(f"{status}\t{path}")
    for p in _untracked(specs):
        dirty.append(f"??\t{p}")
    if dirty:
        sys.stderr.write(
            "Refusing to submit — snapshot surface has uncommitted changes:\n  "
            + "\n  ".join(dirty)
            + "\n\nCommit these so they're captured in the published snapshot.\n"
        )
        raise SystemExit(2)


def collect_overlay_paths(baked_sha: str) -> list[str]:
    """Repo-relative paths to include in the bundle (overlay roots only)."""
    paths: set[str] = set()
    overlay_specs = list(cfg().programs_roots_repo_rel)
    for status, path, src in _name_status(baked_sha, overlay_specs):
        if path and _is_results_path(path):
            continue
        if status == "D" or status.startswith("R"):
            sys.stderr.write(
                f"Refusing to submit — {status} of {src or path}: "
                f"deletions/renames under overlay roots are not supported in v1.\n"
                f"Commit + `helix up --rebuild`.\n"
            )
            raise SystemExit(2)
        if status in ("A", "C", "M"):
            paths.add(path)
    for p in _untracked(overlay_specs):
        if _is_results_path(p):
            continue
        paths.add(p)
    return sorted(paths)


def ensure_config_in_overlay(config_path: str) -> None:
    if not any(_under_root(config_path, r) for r in _overlay_roots()):
        roots = ", ".join(cfg().programs_roots_repo_rel)
        sys.stderr.write(
            f"Config {config_path} must live under an overlay root ({roots})/<p>/<v>/...\n"
        )
        raise SystemExit(2)
    if _is_results_path(config_path):
        sys.stderr.write(f"Config {config_path} cannot be under results/.\n")
        raise SystemExit(2)


def build_tarball(paths: list[str], extra_config_paths: list[str]) -> bytes:
    """Build a tar.gz of the given repo-relative paths."""
    root = Path(repo_root())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        included: set[str] = set()
        for p in [*paths, *extra_config_paths]:
            if p in included:
                continue
            included.add(p)
            abs_p = root / p
            if not abs_p.is_file():
                continue
            tar.add(str(abs_p), arcname=p)
    return buf.getvalue()
