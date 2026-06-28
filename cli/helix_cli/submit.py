"""`helix submit compile|eval` implementations."""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tarfile
from pathlib import Path

import yaml
from rich.console import Console

from . import api, bundle
from .config import job_traces_url, job_ui_url, repo_root, user_id
from .infer import infer_all, infer_program_version, infer_dataset_split


console = Console()


def _repo_relative(p: str) -> str:
    abs_p = os.path.abspath(p)
    rel = os.path.relpath(abs_p, repo_root())
    if rel.startswith(".."):
        sys.stderr.write(f"Config {p} is outside the repo.\n")
        raise SystemExit(2)
    return rel.replace(os.sep, "/")


def _publish_snapshot_fields() -> dict:
    """Publish HEAD's snapshot and return job-metadata fields.

    Load-bearing: the worker materializes the snapshot to run the job, so a
    failure here means the job can't run. Hard-error rather than submit an
    unrunnable job.
    """
    from . import snapshot
    try:
        ref = snapshot.resolve_or_publish(bundle.cfg())
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"Refusing to submit — snapshot publish failed: {e}\n")
        raise SystemExit(3)
    return {
        "snapshot_id": ref["snapshot_id"],
        "snapshot_digest": ref["digest"],
        "helix_runtime_version": bundle.cfg().runtime.helix_version,
    }


def cmd_submit_compile(args: argparse.Namespace) -> int:
    base_sha = bundle.head_sha()
    bundle.check_snapshot_surface_clean(base_sha)
    snap_fields = _publish_snapshot_fields()

    configs_meta = []
    config_rels: list[str] = []
    for cfg_arg in args.configs:
        rel = _repo_relative(cfg_arg)
        bundle.ensure_config_in_overlay(rel)
        program, version, dataset, split = infer_all(repo_root(), rel)
        if args.program:
            program = args.program
        if args.version:
            version = args.version
        config_rels.append(rel)

        entry = {
            "config_path": rel,
            "dataset": dataset,
            "split": split,
        }
        if args.auto_eval:
            entry["auto_eval_config_path"] = _repo_relative(args.auto_eval)
        elif not args.no_auto_eval:
            # default auto-chain: try eval.config.<dataset>_<split>-test.yaml
            # under the first overlay root (program-version dir), config-driven.
            programs_root = bundle.cfg().programs_roots_repo_rel[0]
            candidate = (
                Path(repo_root())
                / programs_root
                / program
                / version
                / f"eval.config.{dataset}_{split}-test.yaml"
            )
            if candidate.is_file():
                entry["auto_eval_config_path"] = str(candidate.relative_to(repo_root()))
        configs_meta.append(entry)

    overlay_paths = bundle.collect_overlay_paths(base_sha)
    bundle_bytes = bundle.build_tarball(overlay_paths, config_rels)

    metadata = {
        "repo_id": bundle.cfg().repo_id,
        "user_id": user_id(),
        "allow_parallel_user_jobs": bool(args.allow_parallel_user_jobs),
        "program": args.program,
        "version": args.version,
        "configs": configs_meta,
        "overlay_files": overlay_paths + config_rels,
        **snap_fields,
    }
    results = api.submit_compile(metadata, bundle_bytes)
    for r in results:
        job_id = r["job_id"]
        console.print(
            f"[green]submitted[/green] {job_id}  label={r['run_label']}  "
            f"ui={job_ui_url(job_id)}  traces={job_traces_url(job_id)}"
        )
    return 0


def cmd_submit_eval(args: argparse.Namespace) -> int:
    base_sha = bundle.head_sha()
    bundle.check_snapshot_surface_clean(base_sha)
    snap_fields = _publish_snapshot_fields()

    # Resolve --compilation to a Helix compile-job id (idempotent import).
    compile_job_id = args.compile_job or _import_legacy_results(args.compilation)

    configs_meta = []
    config_rels: list[str] = []
    for cfg_arg in args.configs:
        rel = _repo_relative(cfg_arg)
        bundle.ensure_config_in_overlay(rel)
        config_rels.append(rel)
        configs_meta.append(
            {
                "config_path": rel,
                "compile_job_id": compile_job_id,
            }
        )

    overlay_paths = bundle.collect_overlay_paths(base_sha)
    bundle_bytes = bundle.build_tarball(overlay_paths, config_rels)

    metadata = {
        "repo_id": bundle.cfg().repo_id,
        "user_id": user_id(),
        "allow_parallel_user_jobs": bool(args.allow_parallel_user_jobs),
        "configs": configs_meta,
        "overlay_files": overlay_paths + config_rels,
        **snap_fields,
    }
    results = api.submit_eval(metadata, bundle_bytes)
    for r in results:
        job_id = r["job_id"]
        console.print(
            f"[green]submitted[/green] {job_id}  label={r['run_label']}  "
            f"ui={job_ui_url(job_id)}  traces={job_traces_url(job_id)}"
        )
    return 0


def _results_path_re() -> "re.Pattern[str]":
    # <overlay_root>/<program>/<version>/results/<NNNN>, config-driven.
    roots = "|".join(re.escape(r) for r in bundle.cfg().programs_roots_repo_rel)
    return re.compile(
        rf"(?:{roots})/(?P<program>[^/]+)/(?P<version>[^/]+)/results/(?P<n>\d{{4}})/?$"
    )


def _import_legacy_results(local_results_dir: str) -> str:
    """Tar a legacy results dir and POST to /jobs/import-compile.

    Returns the resulting compile-job id (idempotent on
    (program_version, emitted_run_number)).
    """
    abs_dir = os.path.abspath(local_results_dir)
    if not os.path.isdir(abs_dir):
        sys.stderr.write(f"--compilation: not a directory: {local_results_dir}\n")
        raise SystemExit(2)

    rel = os.path.relpath(abs_dir, repo_root()).replace(os.sep, "/")
    m = _results_path_re().search(rel + "/")
    if not m:
        roots = ", ".join(bundle.cfg().programs_roots_repo_rel)
        sys.stderr.write(
            f"--compilation must be a path like ({roots})/<p>/<v>/results/<NNNN>/; got {rel!r}\n"
        )
        raise SystemExit(2)
    program = m.group("program")
    version = m.group("version")
    emitted = int(m.group("n"))
    basename = f"{emitted:04d}"

    dataset, split = _infer_legacy_dataset_split(abs_dir)
    if not (dataset and split):
        sys.stderr.write(
            f"--compilation: could not infer dataset/split from {abs_dir}; "
            f"results/<NNNN>/compile/compile.config.yaml must reference a "
            f"data/splits/<dataset>_<split>.yaml path.\n"
        )
        raise SystemExit(2)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in Path(abs_dir).rglob("*"):
            if not p.is_file():
                continue
            r = str(p.relative_to(abs_dir))
            if r.startswith("evals/") or r.startswith("helix/"):
                continue
            tar.add(str(p), arcname=r)
    bundle_bytes = buf.getvalue()

    compile_config_path = None
    for cand in sorted(Path(abs_dir).glob("compile.config*.yaml")):
        compile_config_path = str(cand.relative_to(repo_root()))
        break

    metadata = {
        "repo_id": bundle.cfg().repo_id,
        "user_id": user_id(),
        "program": program,
        "version": version,
        "dataset": dataset,
        "split": split,
        "emitted_run_number": emitted,
        "results_dir_basename": basename,
        "compile_config_path": compile_config_path,
    }
    result = api.import_compile(metadata, bundle_bytes)
    console.print(
        f"[green]imported[/green] {result['job_id']}  "
        f"(program={program} version={version} run={basename})"
    )
    return result["job_id"]


def _infer_legacy_dataset_split(results_dir: str) -> tuple[str | None, str | None]:
    """Read compile/compile.config.yaml inside the legacy dir to find splits path."""
    cfg_path = os.path.join(results_dir, "compile", "compile.config.yaml")
    if not os.path.isfile(cfg_path):
        return None, None
    try:
        doc = yaml.safe_load(Path(cfg_path).read_text())
    except Exception:
        return None, None
    if not isinstance(doc, dict):
        return None, None
    splits = ((doc.get("data") or {}).get("splits")) or ""
    m = re.search(r"(\d+)_(\d+)\.ya?ml$", splits)
    return (m.group(1), m.group(2)) if m else (None, None)
