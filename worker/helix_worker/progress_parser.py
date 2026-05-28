"""Parse the running job's stdout.log into a structured progress dict.

Mirrors the UI's lib/progress.ts (and the original ai-utils progress_viewer):
the worker writes a {phase, compile{}, eval{}} blob into jobs.summary every
heartbeat tick, so the home table can show live, GEPA-aware progress per row
without any per-row log streaming on the client.

Stdlib-only; called from the heartbeat thread, so kept fast (no I/O beyond
one local file read per tick).
"""
from __future__ import annotations

import os
import re
from typing import Any


RE_TQDM = re.compile(
    r"(\d+)/(\d+)\s*\[(\d+:\d+(?::\d+)?|\?)<(\d+:\d+(?::\d+)?|\?),\s*([\d.?]+)([a-zA-Z/]+)\]"
)
RE_ITER_SELECTED = re.compile(r"Iteration (\d+):\s*Selected")
RE_ITER_NEW = re.compile(r"Iteration (\d+):\s*New program candidate index")
RE_BEST_VAL = re.compile(r"Best valset aggregate score so far:\s*([\d.]+)")
RE_PARETO = re.compile(r"Valset pareto front aggregate score:?\s*([\d.]+)")
RE_GEPA_BUDGET = re.compile(r"Running GEPA for approx (\d+) metric calls")
RE_COMPILE_DONE = re.compile(r"Compilation complete|=== eval start")
RE_EVAL_DONE = re.compile(r"=== done|Eval complete|Saved results")
RE_EVAL_STATUS = re.compile(
    r"\[(\d+)/(\d+)\]\s*"
    r"Acc:\s*([\d.]+)%\s*\|\s*"
    r"Tokens:\s*([\d,]+)\s*\(in:([\d,]+)/out:([\d,]+)\)\s*\|\s*"
    r"Cost:\s*\$([\d.]+)\s*\|\s*"
    r"Latency:\s*avg=(\d+)ms,\s*med=(\d+)ms(?:,\s*var=(\d+)ms²)?\s*\|\s*"
    r"ETA:\s*(\S+)"
)


def parse_text(text: str) -> dict[str, Any]:
    eval_matches = list(RE_EVAL_STATUS.finditer(text))
    eval_done = bool(RE_EVAL_DONE.search(text))
    has_eval = bool(eval_matches) or "=== eval start" in text
    compile_done = bool(RE_COMPILE_DONE.search(text)) or has_eval

    if has_eval and not eval_done:
        phase = "eval"
    elif eval_done:
        phase = "done"
    elif compile_done:
        phase = "compile-done"
    else:
        phase = "compile"

    out: dict[str, Any] = {"phase": phase}

    # --- compile (GEPA) -----------------------------------------------------
    rollouts_match = last_tqdm = None
    for m in RE_TQDM.finditer(text):
        last_tqdm = m
        if "rollout" in m.group(6):
            rollouts_match = m
    chosen = rollouts_match or last_tqdm

    budget = RE_GEPA_BUDGET.search(text)
    iters = [int(m.group(1)) for m in RE_ITER_SELECTED.finditer(text)]
    best = [m for m in RE_BEST_VAL.finditer(text)]
    pareto = [m for m in RE_PARETO.finditer(text)]
    wins = sum(1 for _ in RE_ITER_NEW.finditer(text))

    if chosen or iters or budget:
        cur = int(chosen.group(1)) if chosen else None
        total = int(chosen.group(2)) if chosen else None
        out["compile"] = {
            "rolloutsCur": cur,
            "rolloutsTotal": total,
            "rolloutsPct": round(100.0 * cur / total, 1) if cur and total else None,
            "remaining": chosen.group(4) if chosen else None,
            "rate": (chosen.group(5) + chosen.group(6)) if chosen else None,
            "budget": int(budget.group(1)) if budget else None,
            "lastIter": max(iters) if iters else None,
            "bestValset": float(best[-1].group(1)) if best else None,
            "paretoFront": float(pareto[-1].group(1)) if pareto else None,
            "wins": wins,
        }

    # --- eval ---------------------------------------------------------------
    if eval_matches:
        m = eval_matches[-1]
        rows_done = int(m.group(1))
        rows_total = int(m.group(2))
        out["eval"] = {
            "rowsDone": rows_done,
            "rowsTotal": rows_total,
            "rowsPct": round(100.0 * rows_done / rows_total, 1) if rows_total else 0,
            "accPct": float(m.group(3)),
            "costUsd": float(m.group(7)),
            "eta": m.group(11),
        }

    return out


def parse_file(path: str) -> dict[str, Any] | None:
    """Read the job's stdout.log and return a progress dict, or None if absent."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    if not text.strip():
        return None
    return parse_text(text)
