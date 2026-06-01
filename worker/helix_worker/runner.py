"""Run a single claimed job to completion."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import tarfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
import structlog
from sqlalchemy import text

from . import settings, snapshot_cache, venv_cache
from .allocator import allocate_compile_number, allocate_eval_number
from .api_client import submit_eval as api_submit_eval
from .blob import get_bytes
from .claim import fence
from .db import engine
from .overlay import mount_overlay, unmount_overlay
from .upload import upload_bytes_as_artifact, upload_tree


log = structlog.get_logger(__name__)


def _program_version_from_config(cfg, config_path: str) -> tuple[str, str]:
    m = cfg.program_version_re().search(config_path)
    if not m:
        raise RuntimeError(f"cannot infer program/version from {config_path}")
    return m.group(1), m.group(2)


def _cwd_relative_config(cfg, config_path: str) -> str:
    """Entrypoints run with cwd = the merged snapshot root (== the base dir),
    so a repo-relative config path is stripped to base-relative for --config."""
    return cfg.strip_base_prefix(config_path)


def _results_root(merged: str, cfg, program: str, version: str) -> str:
    """<merged>/<overlay_root_base_rel>/<program>/<version>/results.

    The merged overlay root IS the base dir, so the overlay root is taken
    base-relative (e.g. `programs`, not `<base>/programs`)."""
    overlay_root = cfg.strip_base_prefix(cfg.programs_roots_repo_rel[0])
    return os.path.join(merged, *overlay_root.split("/"), program, version, "results")


# -----------------------------------------------------------------------------
# Snapshot resolution / runtime fence (Phase 2)
# -----------------------------------------------------------------------------

def _resolve_snapshot(snapshot_id) -> tuple[str | None, dict, dict]:
    """(digest, seed_state, oob_blobs) for a snapshot_id, or (None, {}, {})."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT digest, seed_state, oob_blobs FROM snapshots WHERE id = :sid"),
            {"sid": snapshot_id},
        ).mappings().first()
    if not row:
        return None, {}, {}
    return row["digest"], (row["seed_state"] or {}), (row["oob_blobs"] or {})


def _load_cfg_from_root(root: str):
    """Authoritative config = the snapshot's embedded .helix/config.toml."""
    from helix_config import load_config
    return load_config(os.path.join(root, ".helix", "config.toml"))


def _runtime_compatible(spec: str | None, version: str) -> bool:
    """Does concrete `version` satisfy the consumer's `spec` (e.g. '>=0.1,<0.2')?

    Tiny stdlib-only constraint check: comma-separated >=,<=,>,<,== clauses
    over dotted numeric versions. An empty/None spec accepts anything.
    """
    if not spec:
        return True
    cur = _ver_tuple(version)
    for clause in spec.split(","):
        clause = clause.strip()
        if not clause:
            continue
        m = re.match(r"(>=|<=|==|>|<)\s*([0-9][0-9.]*)", clause)
        if not m:
            return False
        op, rhs = m.group(1), _ver_tuple(m.group(2))
        if op == ">=" and not cur >= rhs:
            return False
        if op == "<=" and not cur <= rhs:
            return False
        if op == ">" and not cur > rhs:
            return False
        if op == "<" and not cur < rhs:
            return False
        if op == "==" and not cur == rhs:
            return False
    return True


def _ver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def _block(job: dict[str, Any], reason: str) -> None:
    """Park the job in `blocked` (not failed): it is not claimable, so no
    hot-loop, and re-publishing its snapshot flips it back to queued."""
    log.warning("job_blocked", job_id=str(job["id"]), reason=reason)
    fence(
        """
        UPDATE jobs
        SET status='blocked', blocked_reason=:reason,
            worker_id=NULL, lease_expires_at=NULL
        WHERE id = :_job_id_fence AND worker_id = :_worker_id_fence
          AND attempt = :_attempt_fence
        """,
        {"reason": reason},
        job["id"],
        job["attempt"],
    )


def _unblock_digest(digest: str) -> None:
    """A worker just materialized `digest` → any job blocked on a snapshot
    with this digest can run now. Flip them back to queued."""
    with engine.begin() as conn:
        n = conn.execute(
            text(
                """
                UPDATE jobs
                SET status='queued', blocked_reason=NULL,
                    worker_id=NULL, lease_expires_at=NULL
                WHERE status='blocked'
                  AND snapshot_id IN (SELECT id FROM snapshots WHERE digest = :d)
                """
            ),
            {"d": digest},
        ).rowcount
    if n:
        log.info("unblocked_jobs", digest=digest[:12], count=n)


def _prepare(job: dict[str, Any]) -> dict[str, Any] | None:
    """Materialize the job's snapshot, build/locate its venv, load its config.

    Returns a run-context dict, or None if the job was parked `blocked`
    (snapshot unavailable, missing snapshot_id, or runtime-incompatible).
    """
    snapshot_id = job.get("snapshot_id")
    if not snapshot_id:
        _block(job, "job has no snapshot_id (cannot run in snapshot mode)")
        return None
    digest, seed_state, oob_blobs = _resolve_snapshot(snapshot_id)
    if not digest:
        _block(job, f"snapshot {snapshot_id} has no manifest/digest")
        return None
    try:
        root = snapshot_cache.materialize(digest)
        # Out-of-band data blobs become extra overlayfs lowerdirs over the base.
        oob_roots = [
            snapshot_cache.materialize_oob(d) for d in sorted(oob_blobs.values())
        ]
    except snapshot_cache.SnapshotUnavailable as e:
        _block(job, f"snapshot {digest[:12]} unavailable: {e}")
        return None

    # We just proved this digest is materializable: unblock its siblings.
    _unblock_digest(digest)

    cfg = _load_cfg_from_root(root)
    spec = job.get("helix_runtime_version")
    if not _runtime_compatible(spec, settings.HELIX_RUNTIME_VERSION):
        _block(
            job,
            f"worker runtime {settings.HELIX_RUNTIME_VERSION} does not satisfy {spec!r}",
        )
        return None

    venv = venv_cache.ensure_venv(root, cfg)
    # oob lowerdirs layered first (uppermost), base snapshot last.
    lowers = oob_roots + [root]
    return {
        "root": root,
        "lowers": lowers,
        "cfg": cfg,
        "python": venv_cache.venv_python(venv),
        "digest": digest,
        "seed_state": seed_state,
    }


def run_job(job: dict[str, Any]) -> None:
    """Top-level dispatcher. Catches all exceptions and marks the job failed."""
    job_id: uuid.UUID = job["id"]
    attempt: int = job["attempt"]
    work_root = os.path.join(settings.WORK_DIR, str(job_id))
    os.makedirs(work_root, exist_ok=True)

    log.info("job_start", job_id=str(job_id), type=job["type"], attempt=attempt)

    try:
        ctx = _prepare(job)
        if ctx is None:
            return  # parked blocked; nothing more to do
        if job["type"] == "compile":
            _run_compile(job, work_root, ctx)
        else:
            _run_eval(job, work_root, ctx)
    except Exception as e:  # noqa: BLE001
        log.exception("job_failed", job_id=str(job_id), error=str(e))
        # Best-effort: upload stdout.log even on early failures so the user
        # has something to read post-mortem. The SSE log stream has no
        # replay, so without this artifact a malformed-config or
        # missing-file failure leaves no diagnostic trace.
        try:
            log_path = os.path.join(work_root, "stdout.log")
            if os.path.isfile(log_path):
                _upload_stdout(job_id, attempt, log_path)
        except Exception as ue:  # noqa: BLE001
            log.warning("stdout_upload_on_failure_failed", error=str(ue))
        _terminal(job_id, attempt, "failed", exit_code=-1, summary={"error": str(e)})
    finally:
        unmount_overlay(work_root)


# -----------------------------------------------------------------------------
# Compile
# -----------------------------------------------------------------------------

def _run_compile(job: dict[str, Any], work_root: str, ctx: dict[str, Any]) -> None:
    job_id = job["id"]
    attempt = job["attempt"]
    config_path = job["config_path"]
    cfg = ctx["cfg"]
    program, version = _program_version_from_config(cfg, config_path)

    # The materialized snapshot root IS the consumer base dir; the overlay
    # merged root is therefore the base dir (cwd for the entrypoint).
    merged = mount_overlay(ctx["lowers"], work_root)
    _extract_bundle_if_any(job, merged, cfg)

    # Allocate emitted_run_number and seed placeholders. Seed = the max run
    # number captured in the snapshot manifest for this program/version
    # (results/ is excluded from the snapshot, so we can't scan it on disk).
    program_version_id = _program_version_id(job_id)
    seed_max = int(ctx["seed_state"].get(f"{program}/{version}", 0))
    n = allocate_compile_number(program, version, program_version_id, seed_max)
    results_root = _results_root(merged, cfg, program, version)
    _seed_placeholders(results_root, n)
    _set_emitted_run_number(job_id, attempt, n)

    # Spawn compile.py in a new process group via the consumer venv's python.
    # config_path is repo-relative; cwd=merged(base dir) so pass base-relative.
    cwd_rel_config = _cwd_relative_config(cfg, config_path)
    log_path = os.path.join(work_root, "stdout.log")
    rc, cancelled = _spawn_and_stream(
        job_id=job_id,
        cmd=[
            ctx["python"],
            os.path.join(settings.HELIX_RUNTIME_DIR, "compile.py"),
            "--config",
            cwd_rel_config,
        ],
        cwd=merged,
        env=_build_env(job, merged),
        log_path=log_path,
    )

    results_dir = os.path.join(results_root, f"{n:04d}")

    if cancelled:
        # Upload what we have (logs + partial artifacts) and mark cancelled.
        _upload_partial_compile(job_id, attempt, results_dir, log_path)
        _terminal(job_id, attempt, "cancelled", exit_code=rc, summary=_parse_summary(log_path))
        return

    if not os.path.isdir(results_dir):
        raise RuntimeError(
            f"compile.py exited but expected results dir {results_dir} is missing"
        )

    # Worker-side post-run bookkeeping.
    _write_program_hash(results_dir)
    _copy_config_to_root(merged, cfg, config_path, results_dir)

    # Upload artifacts.
    upload_tree(
        job_id=job_id,
        attempt=attempt,
        results_dir=results_dir,
        # compiled_program/ is the single canonical deployable artifact
        # (compile.py's post_compile step writes it for every config); compile/
        # carries inputs/provenance (config, program.py, splits, dataset).
        include_prefixes=("compiled_program/", "compile/", "gepa_logs/"),
        include_root_files=(
            "program.hash",
            os.path.basename(config_path),
            "compile.config.yaml",  # stable alias for /ai-deploy
        ),
    )
    _upload_stdout(job_id, attempt, log_path)

    summary = _parse_summary(log_path)
    if rc == 0:
        _terminal(job_id, attempt, "succeeded", exit_code=0, summary=summary)
        _maybe_auto_eval(job_id, job["repo_id"])
    else:
        _terminal(job_id, attempt, "failed", exit_code=rc, summary=summary)


def _maybe_auto_eval(compile_job_id: uuid.UUID, repo_id: str) -> None:
    """If the API attached `auto_eval_config_path` to this compile's summary
    at submission time, queue the chained eval now that we've succeeded.

    The API inherits repo_id/snapshot/runtime + bundle bytes from the parent
    compile, so we only need to pass repo_id + the eval config path.
    Failures here are logged but never fail the compile.
    """
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT summary FROM jobs WHERE id = :jid"), {"jid": compile_job_id}
        ).mappings().first()
    if not row:
        return
    summary = row["summary"] or {}
    aec = summary.get("auto_eval_config_path")
    if not aec:
        return
    try:
        result = api_submit_eval(
            repo_id=repo_id, config_path=aec, compile_job_id=compile_job_id
        )
        log.info("auto_eval_queued", compile_job_id=str(compile_job_id), result=result)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "auto_eval_submission_failed",
            compile_job_id=str(compile_job_id),
            error=str(e),
        )


# -----------------------------------------------------------------------------
# Eval
# -----------------------------------------------------------------------------

def _run_eval(job: dict[str, Any], work_root: str, ctx: dict[str, Any]) -> None:
    job_id = job["id"]
    attempt = job["attempt"]
    parent_id: uuid.UUID = job["parent_job_id"]
    config_path = job["config_path"]
    cfg = ctx["cfg"]
    program, version = _program_version_from_config(cfg, config_path)

    merged = mount_overlay(ctx["lowers"], work_root)
    _extract_bundle_if_any(job, merged, cfg)

    # Fetch parent compile's emitted_run_number + materialize its artifacts.
    parent_run_number = _parent_emitted_run_number(parent_id)
    parent_results_dir = os.path.join(
        _results_root(merged, cfg, program, version), f"{parent_run_number:04d}"
    )
    _materialize_parent_artifacts(parent_id, parent_results_dir)
    _ensure_data_symlink(merged, program, version, parent_results_dir)

    # Allocate eval number, seed placeholders.
    m = allocate_eval_number(parent_id, parent_results_dir)
    _seed_placeholders(os.path.join(parent_results_dir, "evals"), m)
    _set_emitted_run_number(job_id, attempt, m)

    # Spawn evaluate.py via the consumer venv's python.
    cwd_rel_config = _cwd_relative_config(cfg, config_path)
    log_path = os.path.join(work_root, "stdout.log")
    rc, cancelled = _spawn_and_stream(
        job_id=job_id,
        cmd=[
            ctx["python"],
            os.path.join(settings.HELIX_RUNTIME_DIR, "evaluate.py"),
            "--config",
            cwd_rel_config,
            "--compilation",
            os.path.relpath(parent_results_dir, merged),
        ],
        cwd=merged,
        env=_build_env(job, merged),
        log_path=log_path,
    )

    eval_dir = os.path.join(parent_results_dir, "evals", f"{m:04d}")

    if cancelled:
        _upload_stdout(job_id, attempt, log_path)
        _terminal(job_id, attempt, "cancelled", exit_code=rc, summary=_parse_summary(log_path))
        return

    if not os.path.isdir(eval_dir):
        raise RuntimeError(f"evaluate.py exited but {eval_dir} is missing")

    _write_eval_summary(parent_results_dir, eval_dir)

    upload_tree(
        job_id=job_id,
        attempt=attempt,
        results_dir=parent_results_dir,
        include_prefixes=(f"evals/{m:04d}/",),
        include_root_files=("EVAL_SUMMARY.md",),
    )
    _upload_stdout(job_id, attempt, log_path)

    summary = _parse_summary(log_path)
    if rc == 0:
        _terminal(job_id, attempt, "succeeded", exit_code=0, summary=summary)
    else:
        _terminal(job_id, attempt, "failed", exit_code=rc, summary=summary)


# -----------------------------------------------------------------------------
# Subprocess + cancel
# -----------------------------------------------------------------------------

def _spawn_and_stream(
    *, job_id: uuid.UUID, cmd: list[str], cwd: str, env: dict[str, str], log_path: str
) -> tuple[int, bool]:
    """Returns (returncode, cancel_observed)."""
    rclient = redis.Redis.from_url(settings.HELIX_REDIS_URL, decode_responses=True)
    logs_chan = f"helix:logs:{job_id}"
    cancel_chan = f"helix:cancel:{job_id}"

    log.info("spawn", cmd=cmd, cwd=cwd)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=1,
        text=True,
    )

    cancel_stop = threading.Event()
    cancel_observed = threading.Event()
    cancel_thread = threading.Thread(
        target=_cancel_subscriber,
        args=(rclient, cancel_chan, proc, cancel_stop, cancel_observed),
        daemon=True,
        name=f"cancel-{job_id}",
    )
    cancel_thread.start()

    seq = 0
    with open(log_path, "w", encoding="utf-8") as fp:
        assert proc.stdout is not None
        for line in proc.stdout:
            seq += 1
            fp.write(line)
            fp.flush()
            payload = json.dumps(
                {
                    "seq": seq,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "stream": "stdout",
                    "line": line.rstrip("\n"),
                }
            )
            try:
                rclient.publish(logs_chan, payload)
            except Exception:
                pass

    rc = proc.wait()
    cancel_stop.set()
    return rc, cancel_observed.is_set()


def _cancel_subscriber(
    rclient: "redis.Redis",
    channel: str,
    proc: subprocess.Popen,
    stop: threading.Event,
    cancel_observed: threading.Event,
) -> None:
    pubsub = rclient.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel)
    try:
        while not stop.is_set():
            msg = pubsub.get_message(timeout=1.0)
            if msg is None:
                continue
            if proc.poll() is not None:
                return
            cancel_observed.set()
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                proc.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    return
                proc.wait()
                return
    finally:
        try:
            pubsub.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _extract_bundle_if_any(job: dict[str, Any], merged: str, cfg) -> None:
    """Safely extract the overlay bundle onto the merged snapshot root.

    The CLI's overlay-capture rules already constrain what goes into the
    bundle, but the API accepts arbitrary multipart bytes — anyone hitting
    helix-api directly (no auth in v1) could supply a tar with absolute
    paths, '..' components, symlinks, or files under baked-only roots.
    Since the worker spawns the entrypoints against this tree immediately
    afterward with provider secrets in env, accepting such a tar is
    RCE-equivalent.

    Bundle arcnames are REPO-relative (e.g. <base>/programs/...), but the
    merged root IS the base dir, so each accepted member is rewritten
    base-relative (strip the <base>/ prefix) before extraction.

    Defense:
    - Members must be regular files (no symlinks, hardlinks, devices, dirs).
    - Names must be relative, under one of the configured overlay roots
      (cfg.programs_roots_repo_rel), and contain no '..' segment.
    - Files under <overlay_root>/<p>/<v>/results/ are skipped.
    - The rewritten target must stay inside an overlay root on the merged tree.
    Anything else fails the whole extraction.
    """
    key = job.get("bundle_blob_key")
    if not key:
        return
    raw = get_bytes(key)

    merged_root = os.path.realpath(merged)
    overlay_roots = cfg.programs_roots_repo_rel  # repo-relative
    overlay_roots_base = [cfg.strip_base_prefix(r) for r in overlay_roots]
    allowed_roots = [
        os.path.realpath(os.path.join(merged_root, r)) for r in overlay_roots_base
    ]
    allowed_prefixes = tuple(r.rstrip("/") + "/" for r in overlay_roots)

    def _under_overlay(name: str) -> bool:
        return any(name == r.rstrip("/") or name.startswith(p)
                   for r, p in zip(overlay_roots, allowed_prefixes))

    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        members: list[tarfile.TarInfo] = []
        for m in tar.getmembers():
            if m.isdir():
                continue  # let extract auto-create parent dirs
            if not m.isfile():
                raise RuntimeError(
                    f"bundle member {m.name!r} is not a regular file "
                    f"(type={m.type!r}); refusing extraction"
                )
            name = m.name
            if name.startswith("/") or "\x00" in name:
                raise RuntimeError(f"bundle member has absolute or null path: {name!r}")
            # Reject any traversal segment before normpath collapses it.
            parts = name.replace("\\", "/").split("/")
            if any(p == ".." for p in parts):
                raise RuntimeError(f"bundle member has '..' segment: {name!r}")
            if not _under_overlay(name):
                raise RuntimeError(
                    f"bundle member {name!r} is outside overlay roots {overlay_roots}"
                )
            # Skip results/ paths to match the overlay exclusion.
            is_results = False
            for r in overlay_roots:
                pref = r.rstrip("/") + "/"
                if name.startswith(pref):
                    sub = name[len(pref):].split("/")
                    if len(sub) >= 3 and sub[2] == "results":
                        is_results = True
                    break
            if is_results:
                continue
            # Rewrite repo-relative → base-relative for the merged (base-dir) root.
            base_rel = cfg.strip_base_prefix(name)
            target = os.path.realpath(os.path.join(merged_root, base_rel))
            if not any(
                target == ar or target.startswith(ar + os.sep) for ar in allowed_roots
            ):
                raise RuntimeError(
                    f"bundle member {name!r} resolves outside overlay roots"
                )
            m.name = base_rel
            members.append(m)

        for m in members:
            tar.extract(m, merged_root, set_attrs=False)


def _seed_placeholders(parent_dir: str, target_n: int) -> None:
    """Create empty NNNN dirs from 0001..target_n-1 (those not already present).

    `compile.py` does max(results)+1 = N → must exist at least one entry
    numbered target_n-1 (or no entries to mean N=1).
    """
    os.makedirs(parent_dir, exist_ok=True)
    for i in range(1, target_n):
        d = os.path.join(parent_dir, f"{i:04d}")
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)


def _set_emitted_run_number(job_id: uuid.UUID, attempt: int, n: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs SET emitted_run_number = :n
                WHERE id = :jid AND worker_id = :wid AND attempt = :att
                """
            ),
            {"n": n, "jid": job_id, "wid": settings.WORKER_ID, "att": attempt},
        )


def _program_version_id(job_id: uuid.UUID) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text("SELECT program_version_id FROM jobs WHERE id = :jid"),
                {"jid": job_id},
            ).scalar_one()
        )


def _parent_emitted_run_number(parent_id: uuid.UUID) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text("SELECT emitted_run_number FROM jobs WHERE id = :pid"),
                {"pid": parent_id},
            ).scalar_one()
        )


def _materialize_parent_artifacts(parent_id: uuid.UUID, dest_dir: str) -> None:
    """Download the parent compile's artifacts into dest_dir.

    Filters by the parent's current `jobs.attempt` so partial uploads
    from a prior crashed attempt (same relative_path, lower attempt
    number) don't clobber the succeeded attempt's files in
    nondeterministic order. The succeeded attempt is always the row's
    current `attempt` value — once a job reaches a terminal state the
    `attempt` column is no longer incremented.
    """
    from .blob import _client
    from sqlalchemy import text as _t

    os.makedirs(dest_dir, exist_ok=True)
    with engine.begin() as conn:
        rows = list(
            conn.execute(
                _t(
                    """
                    SELECT relative_path, blob_key
                    FROM artifacts
                    WHERE job_id = :pid
                      AND attempt = (SELECT attempt FROM jobs WHERE id = :pid)
                    """
                ),
                {"pid": parent_id},
            )
        )
    c = _client()
    for rel, blob_key in rows:
        if rel.startswith("helix/"):
            continue
        out_path = os.path.join(dest_dir, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        c.fget_object(settings.HELIX_BLOB_BUCKET, blob_key, out_path)


def _ensure_data_symlink(repo: str, program: str, version: str, results_dir: str) -> None:
    """Recreate the `data` symlink convention so evaluate.py resolves splits."""
    link = os.path.join(results_dir, "data")
    target = "../../data"  # results/NNNN/data → programs/<p>/<v>/data
    if os.path.islink(link) or os.path.exists(link):
        return
    os.symlink(target, link)


def _write_program_hash(results_dir: str) -> None:
    pkl = os.path.join(results_dir, "compile", "compiled_program", "program.pkl")
    if not os.path.isfile(pkl):
        return
    h = hashlib.sha256()
    with open(pkl, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    Path(results_dir, "program.hash").write_text(h.hexdigest() + "\n")


def _copy_config_to_root(merged: str, cfg, config_path: str, results_dir: str) -> None:
    """Mirror the submitted compile config at the results-dir root.

    Writes BOTH the numbered legacy name (e.g. compile.config.0033.yaml,
    matching the convention of the pre-Helix launcher) AND the stable
    alias compile.config.yaml that /ai-deploy reads. Identical content.
    config_path is repo-relative; the merged root is the base dir.
    """
    src = os.path.join(merged, cfg.strip_base_prefix(config_path))
    if not os.path.isfile(src):
        return
    shutil.copy2(src, os.path.join(results_dir, os.path.basename(config_path)))
    # Stable alias for the deploy skill — independent of the numbered basename.
    shutil.copy2(src, os.path.join(results_dir, "compile.config.yaml"))


def _write_eval_summary(results_dir: str, eval_dir: str) -> None:
    """Minimal EVAL_SUMMARY.md generation. Worker is responsible for this.

    Heavier formatting (per-row feedback table) is acceptable in v1 to be
    short; /ai-eval skill historically wrote richer content. Keep this
    parseable by /ai-deploy which only cares about a metrics table.
    """
    results_jsonl = os.path.join(eval_dir, "results.jsonl")
    metrics: dict[str, Any] = {}
    n = 0
    score_sum = 0.0
    if os.path.isfile(results_jsonl):
        with open(results_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if "score" in row and isinstance(row["score"], (int, float)):
                    score_sum += float(row["score"])
                    n += 1
    avg = (score_sum / n * 100.0) if n else 0.0
    metrics["score_pct"] = round(avg, 2)
    metrics["rows"] = n

    md = []
    md.append("# Evaluation Summary\n")
    md.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n")
    md.append("## Metrics\n")
    md.append("| Metric | Value |")
    md.append("|---|---|")
    md.append(f"| Score | {metrics['score_pct']}% |")
    md.append(f"| Rows | {metrics['rows']} |")
    md.append("")
    Path(results_dir, "EVAL_SUMMARY.md").write_text("\n".join(md))


def _upload_partial_compile(job_id: uuid.UUID, attempt: int, results_dir: str, log_path: str) -> None:
    """Best-effort upload of whatever the cancelled compile produced.

    Mirrors `_run_compile`'s post-run upload but tolerates a missing
    results_dir, partial compile/, no gepa_logs/, etc.
    """
    if os.path.isdir(results_dir):
        try:
            upload_tree(
                job_id=job_id,
                attempt=attempt,
                results_dir=results_dir,
                include_prefixes=("compiled_program/", "compile/", "gepa_logs/"),
                include_root_files=("program.hash",),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("partial_compile_upload_failed", error=str(e))
    _upload_stdout(job_id, attempt, log_path)


def _upload_stdout(job_id: uuid.UUID, attempt: int, log_path: str) -> None:
    if not os.path.isfile(log_path):
        return
    data = Path(log_path).read_bytes()
    upload_bytes_as_artifact(
        job_id=job_id, attempt=attempt, rel_path="helix/stdout.log", data=data
    )


def _parse_summary(log_path: str) -> dict[str, Any]:
    """Pull the final `[N/total] Acc: …` line if present."""
    if not os.path.isfile(log_path):
        return {}
    last = ""
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "Acc:" in line and "/" in line:
                last = line.strip()
    if not last:
        return {}
    out: dict[str, Any] = {"status_line": last}
    m_acc = re.search(r"Acc:\s*([\d.]+)%", last)
    if m_acc:
        out["acc_pct"] = float(m_acc.group(1))
    m_cost = re.search(r"Cost:\s*\$([\d.]+)", last)
    if m_cost:
        out["cost_usd"] = float(m_cost.group(1))
    return out


def _build_env(job: dict[str, Any], base_cwd: str) -> dict[str, str]:
    """Env for the spawned compile.py/evaluate.py.

    - HELIX_BASE_DIR: the consumer base dir (entrypoints resolve program code
      from here, not __file__).
    - PYTHONPATH: base dir + helix_runtime so program imports and flat sibling
      imports both resolve.
    - HELIX_RUN_LABEL: generic; KIN_AI_RUN_LABEL kept as a back-compat alias
      for tracing.py until consumers migrate.
    """
    env = os.environ.copy()
    env["HELIX_BASE_DIR"] = base_cwd
    runtime_dir = settings.HELIX_RUNTIME_DIR
    existing_pp = env.get("PYTHONPATH", "")
    parts = [base_cwd, runtime_dir] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["HELIX_RUN_LABEL"] = job["run_label"]
    env["KIN_AI_RUN_LABEL"] = job["run_label"]  # back-compat alias
    return env


def _terminal(
    job_id: uuid.UUID,
    attempt: int,
    status: str,
    *,
    exit_code: int,
    summary: dict[str, Any] | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs
                SET status = :status,
                    ended_at = now(),
                    exit_code = :ec,
                    summary = COALESCE(summary, CAST('{}' AS jsonb)) || CAST(:summary AS jsonb),
                    lease_expires_at = NULL
                WHERE id = :jid AND worker_id = :wid AND attempt = :att
                """
            ),
            {
                "status": status,
                "ec": exit_code,
                "summary": json.dumps(summary or {}),
                "jid": job_id,
                "wid": settings.WORKER_ID,
                "att": attempt,
            },
        )
