"""Content-addressed snapshot: scope the consumer base dir, digest it, publish.

The snapshot is `git archive HEAD -- <base>` with excludes applied, arcnames
rewritten BASE-RELATIVE (so the tar root == the base dir), the resolved
.helix.toml embedded at `.helix/config.toml`. The digest is sha256 of the
canonical UNCOMPRESSED tar bytes (so compression choice never changes
identity); the object is gzip-compressed for transport.

(Plan says zstd; we use gzip to stay stdlib-only — the digest is over the
uncompressed tar, so the compressor is irrelevant to identity.)
"""
from __future__ import annotations

import fnmatch
import gzip
import hashlib
import io
import os
import re
import subprocess
import tarfile
from pathlib import Path

from helix_config import HelixConfig

from . import api, bundle
from .config import repo_root


_RUN_NUMBER_RE = re.compile(r"^\d{4}$")


def _git_archive_bytes(base: str) -> bytes:
    return subprocess.run(
        ["git", "archive", "HEAD", "--", base],
        cwd=repo_root(), check=True, capture_output=True,
    ).stdout


def _excluded(rel: str, cfg: HelixConfig) -> bool:
    """rel is base-relative. Match the .helix.toml exclude globs.

    Excludes are either base-root-anchored ("/tests/") or match-anywhere
    ("**/results/", "**/__pycache__/").
    """
    parts = rel.split("/")
    for pat in cfg.exclude:
        p = pat.strip()
        if p.startswith("/"):
            # root-anchored: <base>/tests/...
            anchor = p.strip("/")
            if rel == anchor or rel.startswith(anchor + "/"):
                return True
        else:
            # match-anywhere on any path segment-dir: **/results/ etc.
            needle = p.replace("**/", "").strip("/")
            if needle and needle in parts:
                return True
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.rstrip("/")):
                return True
    # out_of_band roots are dropped from the snapshot.
    for ob in cfg.out_of_band:
        o = ob.strip("/")
        if rel == o or rel.startswith(o + "/"):
            return True
    return False


def build_snapshot(cfg: HelixConfig) -> tuple[str, bytes, dict]:
    """Return (digest, gzip_tar_bytes, seed_state).

    digest = sha256(uncompressed canonical tar). seed_state maps
    "<program>/<version>" -> max existing results NNNN (so the allocator
    can seed past legacy runs even though results/ is excluded).
    """
    base = cfg.base
    raw = _git_archive_bytes(base)

    # Re-tar base-relative, applying excludes; embed config.
    uncompressed = io.BytesIO()
    seed_state: dict[str, int] = {}
    overlay_rel = [r[len(base) + 1:] if r.startswith(base + "/") else r
                   for r in cfg.programs_roots_repo_rel]  # base-relative overlay roots

    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as src, \
         tarfile.open(fileobj=uncompressed, mode="w", format=tarfile.PAX_FORMAT) as dst:
        for m in sorted(src.getmembers(), key=lambda x: x.name):
            name = m.name
            # git archive prefixes with "<base>/"; strip to base-relative.
            if name == base:
                continue
            if not name.startswith(base + "/"):
                continue
            rel = name[len(base) + 1:]
            if not rel:
                continue
            if _excluded(rel, cfg):
                # but still mine results dirs for seed-state before skipping
                _maybe_seed(rel, overlay_rel, seed_state)
                continue
            m2 = tarfile.TarInfo(name=rel)
            m2.size = m.size
            m2.mtime = 0  # deterministic
            m2.mode = m.mode
            m2.type = m.type
            m2.linkname = m.linkname
            if m.isfile():
                f = src.extractfile(m)
                dst.addfile(m2, f)
            else:
                dst.addfile(m2)

        # Embed the resolved .helix.toml (authoritative config for the job).
        cfg_bytes = _read_config_bytes()
        ci = tarfile.TarInfo(name=".helix/config.toml")
        ci.size = len(cfg_bytes)
        ci.mtime = 0
        dst.addfile(ci, io.BytesIO(cfg_bytes))

    tar_bytes = uncompressed.getvalue()
    digest = hashlib.sha256(tar_bytes).hexdigest()
    gz = gzip.compress(tar_bytes, mtime=0)
    return digest, gz, seed_state


def build_oob_blobs(cfg: HelixConfig) -> dict[str, tuple[str, bytes]]:
    """Build a content-addressed blob per [snapshot].out_of_band root.

    Each root is excluded from the main snapshot (see _excluded) and shipped
    as its own blob with base-relative arcnames (`<oob_root>/...`) so the
    worker can mount it as an extra overlayfs lowerdir over the base tree.

    v1 sources the data from `git archive HEAD -- <base>/<oob_root>` (committed
    data); LFS/DVC/remote fetch is a future extension keyed on the same digest.

    Returns {oob_root: (digest, gzip_tar_bytes)}.
    """
    out: dict[str, tuple[str, bytes]] = {}
    base = cfg.base
    for ob in cfg.out_of_band:
        ob = ob.strip("/")
        pathspec = f"{base}/{ob}"
        raw = subprocess.run(
            ["git", "archive", "HEAD", "--", pathspec],
            cwd=repo_root(), check=True, capture_output=True,
        ).stdout
        uncompressed = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as src, \
             tarfile.open(fileobj=uncompressed, mode="w", format=tarfile.PAX_FORMAT) as dst:
            for m in sorted(src.getmembers(), key=lambda x: x.name):
                name = m.name
                if name == base or not name.startswith(base + "/"):
                    continue
                rel = name[len(base) + 1:]
                if not rel:
                    continue
                m2 = tarfile.TarInfo(name=rel)  # base-relative: <oob_root>/...
                m2.size = m.size
                m2.mtime = 0
                m2.mode = m.mode
                m2.type = m.type
                m2.linkname = m.linkname
                if m.isfile():
                    dst.addfile(m2, src.extractfile(m))
                else:
                    dst.addfile(m2)
        tar_bytes = uncompressed.getvalue()
        digest = hashlib.sha256(tar_bytes).hexdigest()
        out[ob] = (digest, gzip.compress(tar_bytes, mtime=0))
    return out


def _maybe_seed(rel: str, overlay_rel: list[str], seed_state: dict[str, int]) -> None:
    """If rel is <overlay>/<p>/<v>/results/<NNNN>/..., record max NNNN."""
    for ov in overlay_rel:
        pref = ov + "/"
        if rel.startswith(pref):
            sub = rel[len(pref):].split("/")
            if len(sub) >= 4 and sub[2] == "results" and _RUN_NUMBER_RE.match(sub[3]):
                key = f"{sub[0]}/{sub[1]}"
                seed_state[key] = max(seed_state.get(key, 0), int(sub[3]))
            return


def _read_config_bytes() -> bytes:
    from helix_config import CONFIG_FILENAME
    # Walk up like find_config to locate the .helix.toml we resolved from.
    cur = Path(repo_root())
    cand = cur / CONFIG_FILENAME
    return cand.read_bytes()


def _lockfile_digest(cfg: HelixConfig) -> str | None:
    if not cfg.env_lockfile:
        return None
    p = Path(repo_root()) / cfg.env_lockfile
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_snapshot_publish(args) -> int:
    from rich.console import Console
    from helix_config import find_config
    console = Console()
    cfg = find_config(repo_root())
    ref = resolve_or_publish(cfg)
    state = "exists" if ref.get("existed") else "published"
    console.print(f"[green]{state}[/green] snapshot {ref['digest'][:12]}… id={ref['snapshot_id']}")
    return 0


def resolve_or_publish(cfg: HelixConfig) -> dict:
    """Ensure HEAD's snapshot exists; return {snapshot_id, digest}.

    Cheap path: compute digest, ask the API to resolve it; only build+upload
    the tarball if absent.
    """
    digest, gz, seed_state = build_snapshot(cfg)
    ref = api.resolve_snapshot(cfg.repo_id, digest)
    if ref is not None:
        return ref
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root(), check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    # Publish out-of-band data blobs (idempotent), record {root: digest}.
    oob_map: dict[str, str] = {}
    for ob_root, (ob_digest, ob_gz) in build_oob_blobs(cfg).items():
        api.publish_oob(ob_digest, ob_gz)
        oob_map[ob_root] = ob_digest
    meta = {
        "repo_id": cfg.repo_id,
        "digest": digest,
        "git_sha": git_sha,
        "helix_runtime_version": cfg.runtime.helix_version,
        "lockfile_digest": _lockfile_digest(cfg),
        "config_blob": _read_config_bytes().decode("utf-8"),
        "seed_state": seed_state,
        "oob_blobs": oob_map,
    }
    return api.publish_snapshot(meta, gz)
