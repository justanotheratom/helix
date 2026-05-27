"""`helix export <job-id>` — materialize blob artifacts into the legacy results dir."""
from __future__ import annotations

import argparse
import os
import tarfile
import tempfile

from rich.console import Console

from . import api, bundle
from .config import repo_root


console = Console()


def cmd_export(args: argparse.Namespace) -> int:
    job = api.get_job(args.job_id)
    if job["type"] == "compile":
        return _export_compile(job, into=args.into)
    elif job["type"] == "eval":
        parent = api.get_job(str(job["parent_job_id"]))
        _export_compile(parent, into=args.into)
        return _export_eval(job, parent, into=args.into)
    else:
        raise SystemExit(f"unknown job type {job['type']}")


def _results_dir(job: dict, into: str | None) -> str:
    base = into or repo_root()
    # <overlay_root>/<program>/<version>/results/<NNNN>, config-driven.
    programs_root = bundle.cfg().programs_roots_repo_rel[0]
    return os.path.join(
        base,
        *programs_root.split("/"),
        job["program"], job["version"],
        "results",
        f"{job['export_run_number'] or job['emitted_run_number']:04d}",
    )


def _export_compile(job: dict, *, into: str | None) -> int:
    dest = _results_dir(job, into)
    os.makedirs(dest, exist_ok=True)
    dest_real = os.path.realpath(dest)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        api.download_artifacts_tar(str(job["id"]), tmp.name)
        with tarfile.open(tmp.name, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.startswith("helix/"):
                    continue
                _check_safe_member(member, dest_real)
                tar.extract(member, dest, set_attrs=False)
    # data symlink convention.
    link = os.path.join(dest, "data")
    if not (os.path.islink(link) or os.path.exists(link)):
        os.symlink("../../data", link)
    console.print(f"[green]exported compile[/green] {job['id']} → {dest}")
    return 0


def _export_eval(job: dict, parent: dict, *, into: str | None) -> int:
    dest = _results_dir(parent, into)
    os.makedirs(dest, exist_ok=True)
    dest_real = os.path.realpath(dest)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        api.download_artifacts_tar(str(job["id"]), tmp.name)
        with tarfile.open(tmp.name, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.startswith("helix/"):
                    continue
                _check_safe_member(member, dest_real)
                tar.extract(member, dest, set_attrs=False)
    console.print(f"[green]exported eval[/green] {job['id']} → {dest}")
    return 0


def _check_safe_member(member: tarfile.TarInfo, dest_real: str) -> None:
    """Mirror the worker's bundle-extraction guards: no absolute paths,
    no '..', no symlinks/hardlinks, target must stay inside dest_real."""
    if not (member.isfile() or member.isdir()):
        raise SystemExit(f"refusing to extract non-regular member: {member.name!r}")
    name = member.name
    if name.startswith("/") or "\x00" in name:
        raise SystemExit(f"refusing absolute/null path: {name!r}")
    if any(p == ".." for p in name.replace("\\", "/").split("/")):
        raise SystemExit(f"refusing path with '..' segment: {name!r}")
    target = os.path.realpath(os.path.join(dest_real, name))
    if target != dest_real and not target.startswith(dest_real + os.sep):
        raise SystemExit(f"refusing path that escapes export root: {name!r}")
