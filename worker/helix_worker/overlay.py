"""Per-job overlay mount management.

Tries overlayfs first (requires CAP_SYS_ADMIN); falls back to `cp -R`.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import structlog


log = structlog.get_logger(__name__)


def mount_overlay(lower: "str | list[str]", work_root: str) -> str:
    """Mount an overlayfs at `work_root/repo`. Returns that path.

    `lower` may be a single dir or a list. Extra lowerdirs (e.g. out-of-band
    data blobs) are layered OVER the base snapshot — listed left-to-right,
    uppermost first per overlayfs semantics. The roots are disjoint (oob data
    is excluded from the base snapshot), so layering order is immaterial.
    """
    lowers = [lower] if isinstance(lower, str) else list(lower)
    upper = os.path.join(work_root, "upper")
    wd = os.path.join(work_root, "wd")
    repo = os.path.join(work_root, "repo")
    for d in (upper, wd, repo):
        os.makedirs(d, exist_ok=True)
    lowerdir = ":".join(lowers)
    cmd = [
        "mount", "-t", "overlay", "overlay",
        "-o", f"lowerdir={lowerdir},upperdir={upper},workdir={wd}",
        repo,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        log.info("overlay_mounted", repo=repo, lowers=len(lowers))
        return repo
    except Exception as e:
        log.warning("overlay_failed_falling_back_to_cp", error=str(e))
        # Cleanup any half-mounted state.
        try:
            subprocess.run(["umount", repo], capture_output=True)
        except Exception:
            pass
        # Plain cp -R fallback. Never cp -al — hardlinks would corrupt the
        # snapshot. Merge lowers bottom-up (base first, then oob over it).
        if os.path.exists(repo):
            shutil.rmtree(repo)
        for i, l in enumerate(reversed(lowers)):
            if i == 0:
                shutil.copytree(l, repo, symlinks=True)
            else:
                shutil.copytree(l, repo, symlinks=True, dirs_exist_ok=True)
        return repo


def unmount_overlay(work_root: str) -> None:
    repo = os.path.join(work_root, "repo")
    try:
        subprocess.run(["umount", repo], capture_output=True)
    except Exception:
        pass
    try:
        shutil.rmtree(work_root)
    except Exception:
        pass
