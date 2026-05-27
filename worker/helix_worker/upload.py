"""Walk a results-dir subtree and upload artifacts (fenced by worker_id+attempt)."""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from . import settings
from .blob import put_file
from .db import engine


def classify(rel_path: str) -> str:
    if rel_path.startswith("helix/"):
        if rel_path.endswith("stdout.log"):
            return "stdout_log"
        return "other"
    if rel_path == "program.hash":
        return "program_hash"
    if rel_path == "EVAL_SUMMARY.md":
        return "eval_summary_md"
    if rel_path.endswith(".yaml") and "/" not in rel_path:
        return "config"
    if rel_path.startswith("compile/compiled_program/program.pkl"):
        return "compiled_program"
    if rel_path.startswith("gepa_logs/"):
        return "gepa_log"
    if rel_path.endswith("/results.jsonl"):
        return "results_jsonl"
    if rel_path.endswith("/metrics.py"):
        return "metrics_py"
    if rel_path.endswith("/program.py"):
        return "program_py"
    return "other"


def upload_tree(
    *,
    job_id: uuid.UUID,
    attempt: int,
    results_dir: str,
    include_prefixes: tuple[str, ...],
    include_root_files: tuple[str, ...] = (),
) -> int:
    """Walk `results_dir`, upload every file whose relative path starts with one
    of `include_prefixes` (e.g. ('compile/', 'gepa_logs/')) or whose
    relative path matches one of `include_root_files` (e.g. ('program.hash',)).
    Returns the number of artifacts inserted.
    """
    uploaded = 0
    now = datetime.now(timezone.utc)

    for root, _dirs, files in os.walk(results_dir):
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel = os.path.relpath(abs_path, results_dir)
            rel = rel.replace(os.sep, "/")
            if rel in include_root_files or any(rel.startswith(p) for p in include_prefixes):
                if _insert_artifact(job_id, attempt, results_dir, abs_path, rel, now):
                    uploaded += 1
    return uploaded


def _insert_artifact(
    job_id: uuid.UUID, attempt: int, results_dir: str, abs_path: str, rel: str, ts
) -> bool:
    size = os.path.getsize(abs_path)
    sha = _sha256_file(abs_path)
    blob_key = f"artifacts/{job_id}/{attempt}/{rel}"
    put_file(blob_key, abs_path)
    kind = classify(rel)

    sql = text(
        """
        INSERT INTO artifacts (
            job_id, relative_path, kind, blob_key, size_bytes, sha256, mime, attempt, created_at
        )
        SELECT :jid, :rel, :kind, :bk, :sz, :sha, NULL, :att, :ts
        WHERE EXISTS (
            SELECT 1 FROM jobs
            WHERE id = :jid AND worker_id = :wid AND attempt = :att
        )
        ON CONFLICT (job_id, attempt, relative_path) DO NOTHING
        """
    )
    with engine.begin() as conn:
        result = conn.execute(
            sql,
            {
                "jid": job_id,
                "rel": rel,
                "kind": kind,
                "bk": blob_key,
                "sz": size,
                "sha": sha,
                "att": attempt,
                "wid": settings.WORKER_ID,
                "ts": ts,
            },
        )
    return (result.rowcount or 0) > 0


def upload_bytes_as_artifact(
    *, job_id: uuid.UUID, attempt: int, rel_path: str, data: bytes
) -> None:
    """For synthetic artifacts (stdout log)."""
    from .blob import put_bytes

    sha = hashlib.sha256(data).hexdigest()
    blob_key = f"artifacts/{job_id}/{attempt}/{rel_path}"
    put_bytes(blob_key, data)

    sql = text(
        """
        INSERT INTO artifacts (
            job_id, relative_path, kind, blob_key, size_bytes, sha256, mime, attempt, created_at
        )
        SELECT :jid, :rel, :kind, :bk, :sz, :sha, :mime, :att, now()
        WHERE EXISTS (
            SELECT 1 FROM jobs
            WHERE id = :jid AND worker_id = :wid AND attempt = :att
        )
        ON CONFLICT (job_id, attempt, relative_path) DO NOTHING
        """
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "jid": job_id,
                "rel": rel_path,
                "kind": classify(rel_path),
                "bk": blob_key,
                "sz": len(data),
                "sha": sha,
                "mime": "text/plain" if rel_path.endswith(".log") else None,
                "att": attempt,
                "wid": settings.WORKER_ID,
            },
        )


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
