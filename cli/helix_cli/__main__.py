"""`helix` CLI entrypoint."""
from __future__ import annotations

import argparse
import sys

from .doctor import cmd_doctor
from .export import cmd_export
from .init import cmd_init
from .snapshot import cmd_snapshot_publish
from .jobs import cmd_cancel, cmd_list, cmd_logs, cmd_open, cmd_status, cmd_traces
from .stack import cmd_bootstrap, cmd_dev_restart, cmd_dev_up, cmd_down, cmd_gc, cmd_status as cmd_stack_status, cmd_up
from .submit import cmd_submit_compile, cmd_submit_eval


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="helix", description="Helix job runner CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Scaffold a consumer .helix.toml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser("doctor", help="Audit standalone-readiness (no consumer coupling)")
    doctor.set_defaults(func=cmd_doctor)

    gc = sub.add_parser("gc", help="Reclaim storage (unreferenced snapshots + orphan bundles)")
    gc.add_argument("--grace-hours", type=int, default=24)
    gc.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    gc.set_defaults(func=cmd_gc)

    bs = sub.add_parser("bootstrap", help="Interactive .env setup")
    bs.add_argument("--force", action="store_true")
    bs.set_defaults(func=cmd_bootstrap)

    up = sub.add_parser("up", help="Bring the stack up (build images if missing)")
    up.add_argument("--rebuild", action="store_true")
    up.set_defaults(func=cmd_up)

    dev = sub.add_parser("dev", help="Helix-repo dev commands (bind-mounted source)")
    dev_sub = dev.add_subparsers(dest="dev_cmd", required=True)
    dev_up = dev_sub.add_parser(
        "up", help="Up with source bind-mounted (api hot-reloads); no rebuild needed"
    )
    dev_up.add_argument("--rebuild", action="store_true", help="force-rebuild the base image (deps/Dockerfile changed)")
    dev_up.set_defaults(func=cmd_dev_up)
    dev_restart = dev_sub.add_parser(
        "restart", help="Restart worker/api to pick up code edits (no rebuild)"
    )
    dev_restart.add_argument("services", nargs="*", help="default: helix-worker")
    dev_restart.set_defaults(func=cmd_dev_restart)

    dn = sub.add_parser("down", help="Tear the stack down (volumes retained)")
    dn.set_defaults(func=cmd_down)

    st = sub.add_parser("status", help="Stack status, or detail for <job-id>")
    st.add_argument("job_id", nargs="?")
    st.set_defaults(func=lambda a: cmd_status(a) if a.job_id else cmd_stack_status(a))

    submit_p = sub.add_parser("submit", help="Submit compile or eval job(s)")
    submit_sub = submit_p.add_subparsers(dest="kind", required=True)

    sc = submit_sub.add_parser("compile")
    sc.add_argument("configs", nargs="+")
    sc.add_argument("--program")
    sc.add_argument("--version")
    sc.add_argument("--auto-eval")
    sc.add_argument("--no-auto-eval", action="store_true")
    sc.set_defaults(func=cmd_submit_compile)

    se = submit_sub.add_parser("eval")
    se.add_argument("configs", nargs="+")
    src = se.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--compile-job",
        help="Helix compile-job UUID this eval runs against.",
    )
    src.add_argument(
        "--compilation",
        help=(
            "Path to a legacy <programs-root>/<p>/<v>/results/<NNNN>/ "
            "directory. CLI imports it via /jobs/import-compile (idempotent) "
            "and uses the resulting job id as --compile-job."
        ),
    )
    se.set_defaults(func=cmd_submit_eval)

    ls = sub.add_parser("list", help="List jobs with optional filters")
    ls.add_argument("--program")
    ls.add_argument("--version")
    ls.add_argument("--dataset")
    ls.add_argument("--split")
    ls.add_argument("--status")
    ls.add_argument("--type", choices=["compile", "eval"])
    ls.add_argument("--limit", type=int, default=100)
    ls.set_defaults(func=cmd_list)

    lg = sub.add_parser("logs", help="Stream live logs for a job")
    lg.add_argument("job_id")
    lg.add_argument("-f", "--follow", action="store_true")
    lg.set_defaults(func=cmd_logs)

    cn = sub.add_parser("cancel", help="Cancel a queued or running job")
    cn.add_argument("job_id")
    cn.set_defaults(func=cmd_cancel)

    op = sub.add_parser("open", help="Open the UI (job detail if id given)")
    op.add_argument("job_id", nargs="?")
    op.set_defaults(func=cmd_open)

    tr = sub.add_parser("traces", help="Open the Helix trace view for a job")
    tr.add_argument("job_id")
    tr.set_defaults(func=cmd_traces)

    ex = sub.add_parser("export", help="Materialize legacy results dir for a job")
    ex.add_argument("job_id")
    ex.add_argument("--into", help="Destination root (default: repo root)")
    ex.set_defaults(func=cmd_export)

    snap = sub.add_parser("snapshot", help="Content-addressed repo snapshots")
    snap_sub = snap.add_subparsers(dest="snap_cmd", required=True)
    sp_pub = snap_sub.add_parser("publish", help="Publish HEAD's scoped snapshot (idempotent)")
    sp_pub.set_defaults(func=cmd_snapshot_publish)

    return p


def main() -> int:
    p = build_parser()
    args = p.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
