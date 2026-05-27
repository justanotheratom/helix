"""Helix configuration loader — the single source of truth for all
consumer-repo-specific paths and settings.

Dependency-free (stdlib `tomllib` + dataclasses) so it can be vendored
identically into the CLI package and the api / worker images without
pulling pydantic into the CLI.

A consumer repo declares a `.helix.toml` at its root. Helix code reads
*only* this config — it must contain no hardcoded consumer paths
(no consumer path literals). See the plan's "No-coupling gate".

Resolution order:
- CLI (runs in the consumer worktree): `find_config()` walks up from cwd
  to the nearest `.helix.toml`.
- worker / api (run inside a container with the baked repo snapshot):
  `load_config(HELIX_CONFIG_PATH)` where the env var points at the baked
  copy (Phase 1: `/repo-snapshot/.helix.toml`; Phase 2: the snapshot
  manifest's embedded `.helix/config.toml`).
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_FILENAME = ".helix.toml"


class HelixConfigError(RuntimeError):
    """Raised when the config is missing or invalid."""


@dataclass(frozen=True)
class StackConfig:
    host_port: int = 7000
    langfuse_port: int = 3010
    langfuse_minio_port: int = 9090
    langfuse_project_id: str = "helix"


@dataclass(frozen=True)
class RuntimeConfig:
    helix_version: str = ">=0.1,<0.2"
    python: str = "3.13"


@dataclass(frozen=True)
class HelixConfig:
    repo_id: str
    # snapshot
    base: str                                 # base dir, repo-relative (the PYTHONPATH root)
    exclude: tuple[str, ...]
    out_of_band: tuple[str, ...]
    # overlay
    overlay_roots: tuple[str, ...]            # base-relative, e.g. ("programs",)
    # env
    env_manager: str
    env_lockfile: str | None                  # repo-relative
    # nested
    runtime: RuntimeConfig
    stack: StackConfig
    # provenance
    source_path: Path | None = field(default=None, compare=False)

    # ---- derived helpers (no consumer literal ever hardcoded elsewhere) ----

    @property
    def compose_project(self) -> str:
        return f"{self.repo_id}-helix"

    @property
    def programs_roots_repo_rel(self) -> tuple[str, ...]:
        """Overlay roots as repo-relative pathspecs (for `git`)."""
        return tuple(f"{self.base}/{r}".rstrip("/") for r in self.overlay_roots)

    def program_version_re(self) -> re.Pattern[str]:
        """Matches `<base>/<overlay_root>/<program>/<version>/...` (repo-relative)
        OR `<overlay_root>/<program>/<version>/...` (base-relative).

        Built from config so no consumer path literal lives in code.
        Group 1 = program, group 2 = version.
        """
        alts = []
        for r in self.overlay_roots:
            base_rel = re.escape(f"{r}".strip("/"))
            repo_rel = re.escape(f"{self.base}/{r}".strip("/"))
            alts.append(repo_rel)
            alts.append(base_rel)
        # longest-first so repo-relative wins over base-relative
        alts = sorted(set(alts), key=len, reverse=True)
        return re.compile(r"(?:%s)/([^/]+)/([^/]+)/" % "|".join(alts))

    def strip_base_prefix(self, repo_rel_path: str) -> str:
        """Strip the configured base prefix: <base>/programs/x.yaml -> programs/x.yaml.

        Replaces the previously hardcoded base-prefix strip in runner.py.
        """
        prefix = f"{self.base}/"
        return repo_rel_path[len(prefix):] if repo_rel_path.startswith(prefix) else repo_rel_path


def _as_str_tuple(value, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise HelixConfigError(f"{where} must be a list of strings")
    return tuple(value)


def parse_config(data: dict, source_path: Path | None = None) -> HelixConfig:
    if "repo_id" not in data or not isinstance(data["repo_id"], str) or not data["repo_id"]:
        raise HelixConfigError("`repo_id` (string) is required at the top level")
    repo_id = data["repo_id"]
    # repo_id is used as a MinIO object-key segment — keep it safe.
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", repo_id):
        raise HelixConfigError(
            f"repo_id {repo_id!r} must match [a-z0-9][a-z0-9_-]{{0,63}} "
            "(safe object-key segment; no slashes/traversal)"
        )

    snap = data.get("snapshot") or {}
    base = snap.get("base")
    if not isinstance(base, str) or not base:
        raise HelixConfigError("`[snapshot].base` (string) is required")
    base = base.strip("/")

    out_of_band = _as_str_tuple(snap.get("out_of_band"), where="[snapshot].out_of_band")

    overlay = data.get("overlay") or {}
    overlay_roots = _as_str_tuple(overlay.get("roots"), where="[overlay].roots")
    if not overlay_roots:
        raise HelixConfigError("`[overlay].roots` must list at least one base-relative root")
    overlay_roots = tuple(r.strip("/") for r in overlay_roots)

    env = data.get("env") or {}
    runtime_d = data.get("runtime") or {}
    stack_d = data.get("stack") or {}

    return HelixConfig(
        repo_id=repo_id,
        base=base,
        exclude=_as_str_tuple(snap.get("exclude"), where="[snapshot].exclude"),
        out_of_band=out_of_band,
        overlay_roots=overlay_roots,
        env_manager=str(env.get("manager", "uv")),
        env_lockfile=env.get("lockfile"),
        runtime=RuntimeConfig(
            helix_version=str(runtime_d.get("helix_version", RuntimeConfig.helix_version)),
            python=str(runtime_d.get("python", RuntimeConfig.python)),
        ),
        stack=StackConfig(
            host_port=int(stack_d.get("host_port", StackConfig.host_port)),
            langfuse_port=int(stack_d.get("langfuse_port", StackConfig.langfuse_port)),
            langfuse_minio_port=int(stack_d.get("langfuse_minio_port", StackConfig.langfuse_minio_port)),
            langfuse_project_id=str(stack_d.get("langfuse_project_id", StackConfig.langfuse_project_id)),
        ),
        source_path=source_path,
    )


def load_config(path: str | os.PathLike) -> HelixConfig:
    p = Path(path)
    if not p.is_file():
        raise HelixConfigError(
            f"Helix config not found at {p}. Run `helix init` to scaffold a {CONFIG_FILENAME}."
        )
    with p.open("rb") as f:
        data = tomllib.load(f)
    return parse_config(data, source_path=p)


def find_config(start: str | os.PathLike | None = None) -> HelixConfig:
    """Walk up from `start` (default cwd) to the nearest .helix.toml."""
    cur = Path(start or os.getcwd()).resolve()
    for d in (cur, *cur.parents):
        cand = d / CONFIG_FILENAME
        if cand.is_file():
            return load_config(cand)
    raise HelixConfigError(
        f"No {CONFIG_FILENAME} found in {cur} or any parent. "
        "Run `helix init` at your repo root to scaffold one."
    )


def load_from_env() -> HelixConfig:
    """For containers: HELIX_CONFIG_PATH points at the baked config copy."""
    path = os.environ.get("HELIX_CONFIG_PATH")
    if not path:
        raise HelixConfigError("HELIX_CONFIG_PATH is not set in this container")
    return load_config(path)
