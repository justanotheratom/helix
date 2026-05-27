"""Materialize a content-addressed snapshot into a local cache dir.

Replaces the baked /repo-snapshot: the worker downloads the snapshot tarball
from MinIO, verifies its digest, defensively extracts it (same anti-traversal
guards as bundle extraction), and atomically renames it into place. The
resulting `<cache>/<digest>/root` is used as the overlayfs lowerdir.

Concurrent workers race safely: each extracts to a private temp dir and
atomic-renames; the first wins, the rest discard their temp.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
import shutil
import tarfile
import tempfile

import structlog

from . import settings
from .blob import get_bytes

log = structlog.get_logger(__name__)

SNAPSHOT_CACHE = os.environ.get("HELIX_SNAPSHOT_CACHE", "/var/lib/helix/snapshots")
OOB_CACHE = os.environ.get("HELIX_OOB_CACHE", "/var/lib/helix/oob")


def _object_key(digest: str) -> str:
    return f"snapshots/{digest}.tar.gz"


def _oob_key(digest: str) -> str:
    return f"oob/{digest}.tar.gz"


def materialize(digest: str) -> str:
    """Ensure `<snapshot-cache>/<digest>/root` exists; return that path.

    Raises SnapshotUnavailable if the object is missing or the digest doesn't
    verify — the caller marks the job `blocked` (not failed) so it can retry
    once the snapshot is published.
    """
    return _materialize(digest, SNAPSHOT_CACHE, _object_key(digest), "snapshot")


def materialize_oob(digest: str) -> str:
    """Ensure the out-of-band data blob `<oob-cache>/<digest>/root` exists.

    Same verify+defensive-extract path as snapshots; mounted by the caller as
    an extra overlayfs lowerdir over the base snapshot."""
    return _materialize(digest, OOB_CACHE, _oob_key(digest), "oob")


def _materialize(digest: str, cache_dir: str, object_key: str, what: str) -> str:
    root = os.path.join(cache_dir, digest, "root")
    if os.path.isdir(root):
        return root

    os.makedirs(cache_dir, exist_ok=True)
    try:
        gz = get_bytes(object_key)
    except Exception as e:  # noqa: BLE001
        raise SnapshotUnavailable(f"{what} object {digest} not fetchable: {e}") from e

    tar_bytes = gzip.decompress(gz)
    actual = hashlib.sha256(tar_bytes).hexdigest()
    if actual != digest:
        raise SnapshotUnavailable(
            f"{what} digest mismatch: object hashes to {actual}, expected {digest}"
        )

    tmp = tempfile.mkdtemp(prefix=f".{digest[:12]}-", dir=cache_dir)
    tmp_root = os.path.join(tmp, "root")
    os.makedirs(tmp_root, exist_ok=True)
    _safe_extract(tar_bytes, tmp_root)

    final_dir = os.path.join(cache_dir, digest)
    try:
        os.rename(tmp, final_dir)  # atomic on same filesystem
    except OSError:
        # Another worker won the race; discard ours.
        if os.path.isdir(root):
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            raise
    return root


def _safe_extract(tar_bytes: bytes, dest_root: str) -> None:
    """Extract with the same defenses as bundle extraction: regular files +
    dirs only, no absolute/'..'/symlink, targets stay under dest_root."""
    dest_real = os.path.realpath(dest_root)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        for m in tar.getmembers():
            if m.isdir():
                continue
            if not m.isfile():
                raise SnapshotUnavailable(
                    f"snapshot member {m.name!r} is not a regular file (type={m.type!r})"
                )
            name = m.name
            if name.startswith("/") or "\x00" in name:
                raise SnapshotUnavailable(f"snapshot member absolute/null path: {name!r}")
            if any(p == ".." for p in name.replace("\\", "/").split("/")):
                raise SnapshotUnavailable(f"snapshot member has '..': {name!r}")
            target = os.path.realpath(os.path.join(dest_real, name))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise SnapshotUnavailable(f"snapshot member escapes root: {name!r}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            f = tar.extractfile(m)
            with open(target, "wb") as out:
                shutil.copyfileobj(f, out)


def read_embedded_config(snapshot_root: str) -> str | None:
    """Return the embedded .helix/config.toml text, or None."""
    p = os.path.join(snapshot_root, ".helix", "config.toml")
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    return None


class SnapshotUnavailable(RuntimeError):
    """Snapshot can't be materialized right now (missing/corrupt). The job
    should go `blocked`, not `failed`."""
