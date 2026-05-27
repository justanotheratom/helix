"""DB-backed legacy run-number allocator.

Convention: next_number stores the value the NEXT allocation will return.
Seed = max(observed) + 1 on the first allocation; the INSERT branch bumps to max+2.
"""
from __future__ import annotations

import os
import re
import uuid

from sqlalchemy import text

from .db import engine


_RUN_NUMBER_RE = re.compile(r"^\d{4}$")


def _scan_max_existing(path: str) -> int:
    """Return the highest NNNN dir under `path`, or 0 if none."""
    if not os.path.isdir(path):
        return 0
    nums = [int(n) for n in os.listdir(path) if _RUN_NUMBER_RE.match(n)]
    return max(nums) if nums else 0


def allocate_compile_number(
    program: str, version: str, program_version_id: int, seed_max: int = 0
) -> int:
    """Allocate the next results/<NNNN> for a compile job.

    `results/` is excluded from the content-addressed snapshot, so the
    on-disk scan is gone; `seed_max` comes from the snapshot manifest's
    captured per-(program,version) max run number. On a CONFLICT we don't
    just bump (existing + 1) — we GREATEST against (seed_max + 1) so a
    manifest seeded higher than the DB forces the allocator to skip past it,
    matching `compile.py`'s own max+1 behavior and keeping the recorded
    number consistent with the emitted results dir. DB-authoritative
    thereafter.
    """
    sql = text(
        """
        INSERT INTO legacy_compile_run_numbers (program_version_id, next_number)
        VALUES (:pv, :seed_plus_one + 1)
        ON CONFLICT (program_version_id)
        DO UPDATE SET next_number = GREATEST(
            legacy_compile_run_numbers.next_number + 1,
            :seed_plus_one + 1
        )
        RETURNING next_number - 1
        """
    )
    with engine.begin() as conn:
        n = conn.execute(sql, {"pv": program_version_id, "seed_plus_one": seed_max + 1}).scalar_one()
    return int(n)


def allocate_eval_number(compile_job_id: uuid.UUID, parent_results_dir_for_seed: str) -> int:
    """Allocate the next evals/<NNNN> for an eval job.

    Same GREATEST clamp as compile allocation — if the parent's
    materialized results dir already contains higher evals/<NNNN>, the
    allocator must skip past them rather than reusing a stale slot.
    """
    seed_max = _scan_max_existing(os.path.join(parent_results_dir_for_seed, "evals"))
    sql = text(
        """
        INSERT INTO legacy_eval_run_numbers (compile_job_id, next_number)
        VALUES (:cid, :seed_plus_one + 1)
        ON CONFLICT (compile_job_id)
        DO UPDATE SET next_number = GREATEST(
            legacy_eval_run_numbers.next_number + 1,
            :seed_plus_one + 1
        )
        RETURNING next_number - 1
        """
    )
    with engine.begin() as conn:
        n = conn.execute(sql, {"cid": compile_job_id, "seed_plus_one": seed_max + 1}).scalar_one()
    return int(n)
