"""`helix list / status / logs / cancel / open / traces`."""
from __future__ import annotations

import argparse
import json
import webbrowser

from rich.console import Console
from rich.table import Table

from . import api
from .config import HELIX_BASE_URL


console = Console()


def cmd_list(args: argparse.Namespace) -> int:
    rows = api.list_jobs(
        program=args.program, version=args.version, dataset=args.dataset,
        split=args.split, status=args.status, type=args.type, limit=args.limit,
    )
    t = Table(title=f"helix jobs ({len(rows)})", show_lines=False, expand=True)
    for col in ("id", "type", "status", "program", "version", "dataset", "split", "started_at", "summary"):
        t.add_column(col, overflow="fold")
    for r in rows:
        summary = r.get("summary") or {}
        s = " ".join(
            f"{k}={summary[k]}" for k in ("acc_pct", "cost_usd", "rows") if k in summary
        )
        t.add_row(
            str(r["id"])[:8], r["type"], r["status"],
            r.get("program") or "-", r.get("version") or "-",
            r.get("dataset") or "-", r.get("split") or "-",
            r.get("started_at") or "-", s,
        )
    console.print(t)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    job = api.get_job(args.job_id)
    console.print_json(json.dumps(job))
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    if not args.follow:
        console.print("[yellow]Live log only; no replay in v1. Pass -f to tail.[/yellow]")
        return 0
    for event in api.stream_logs(args.job_id):
        line = event.get("line", "")
        console.print(line)
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    job = api.cancel_job(args.job_id)
    console.print(f"[yellow]cancelled[/yellow] {job['id']} status={job['status']}")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    url = HELIX_BASE_URL if not args.job_id else f"{HELIX_BASE_URL}/jobs/{args.job_id}"
    webbrowser.open(url)
    console.print(f"opened {url}")
    return 0


def cmd_traces(args: argparse.Namespace) -> int:
    job = api.get_job(args.job_id)
    url = job["traces_url"]
    webbrowser.open(url)
    console.print(f"opened {url}")
    return 0
