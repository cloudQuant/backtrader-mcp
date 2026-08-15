"""Trusted local control plane and stdio entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from .errors import NotFound, ProductError
from .jobs import job_summary
from .logging_config import configure_logging
from .service import BacktraderMCPService
from .settings import Settings

_LIST_OBJECT_KINDS = ("job", "draft", "dataset", "run_plan", "approval", "audit")
_SHOW_OBJECT_KINDS = ("job", "draft", "dataset", "run_plan")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backtrader-mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="run the local MCP stdio server")
    subparsers.add_parser(
        "doctor",
        help="diagnose this installation, configured roots, and Backtrader runtimes",
    )
    subparsers.add_parser(
        "install-backtrader",
        help="install pinned cloudQuant/backtrader when Backtrader is absent",
    )
    approval = subparsers.add_parser(
        "approve", help="create a trusted local approval record for a prepared change"
    )
    subject = approval.add_mutually_exclusive_group(required=True)
    subject.add_argument("--change-set")
    subject.add_argument("--run-plan")
    approval.add_argument("--change-token")
    approval.add_argument("--run-token")
    approval.add_argument(
        "--yes",
        action="store_true",
        help="confirm after reviewing the prepared hashes (required without a TTY prompt)",
    )
    subparsers.add_parser("audit-independence", help="verify independent product boundaries")
    subparsers.add_parser("recover", help="run startup recovery and print recovered objects")

    list_parser = subparsers.add_parser("list", help="list product objects")
    list_parser.add_argument("--kind", required=True, choices=_LIST_OBJECT_KINDS)
    list_parser.add_argument("--state", help="filter jobs by state (e.g. RUNNING, ORPHANED)")
    list_parser.add_argument("--limit", type=int, default=50)

    show_parser = subparsers.add_parser("show", help="show one object as JSON")
    show_parser.add_argument("--kind", required=True, choices=_SHOW_OBJECT_KINDS)
    show_parser.add_argument("--id", required=True)

    logs_parser = subparsers.add_parser("logs", help="print captured logs for a job")
    logs_parser.add_argument("--job", required=True)

    clean_parser = subparsers.add_parser(
        "clean", help="delete old audit/idempotency/jobs/cas/drafts/approvals records before a date"
    )
    clean_parser.add_argument(
        "--kind",
        required=True,
        choices=("audit", "idempotency", "jobs", "cas", "drafts", "approvals", "nonces"),
    )
    clean_parser.add_argument(
        "--before", required=True, help="ISO date YYYY-MM-DD (records older than this are deleted)"
    )
    return parser


def _list_objects(
    service: BacktraderMCPService, kind: str, state_filter: str | None, limit: int
) -> dict[str, Any]:
    items: list[dict[str, Any]]
    if kind == "approval":
        items = service.state.list_approvals()
    elif kind == "audit":
        items = service.state.list_audit(limit)
    else:
        items = service.state.list(kind)
        if kind == "job":
            if state_filter:
                items = [job for job in items if job.get("state") == state_filter]
            # Newest-first, matching the MCP list_jobs ordering.
            items = sorted(items, key=lambda job: job.get("created_at", ""), reverse=True)
            items = [job_summary(job) for job in items]
    return {"kind": kind, "count": len(items), "items": items[:limit]}


def _show_object(service: BacktraderMCPService, kind: str, object_id: str) -> dict[str, Any]:
    if kind == "job":
        return service.jobs.get_run_status(object_id)
    if kind == "draft":
        return service.drafts.get_draft(object_id)
    if kind == "dataset":
        return service.datasets.get_dataset(object_id)
    return service.state.get("run_plan", object_id)


def _print_job_logs(service: BacktraderMCPService, job_id: str) -> int:
    if service.state.maybe_get("job", job_id) is None:
        raise NotFound(f"job not found: {job_id}")
    job_root = service.settings.state_root / "jobs" / job_id
    log_names = [
        "supervisor.stderr.log",
        "supervisor.stdout.log",
        "candidate.runonce.stderr.log",
        "candidate.runnext.stderr.log",
        "candidate.runonce.stdout.log",
        "candidate.runnext.stdout.log",
    ]
    found = False
    for name in log_names:
        path = job_root / name
        if path.is_file():
            found = True
            print(f"===== {name} =====", file=sys.stderr)
            sys.stderr.write(path.read_text(encoding="utf-8", errors="replace"))
            sys.stderr.write("\n")
    if not found:
        print(f"no log files found for job {job_id}", file=sys.stderr)
    return 0


def _clean_records(service: BacktraderMCPService, kind: str, before: str) -> dict[str, Any]:
    if kind == "jobs":
        result = service.jobs.clean_jobs(before)
        return {"kind": kind, "before": before, **result}
    if kind == "cas":
        result = service.datasets.clean_cas(before)
        return {"kind": kind, "before": before, **result}
    if kind == "drafts":
        result = service.drafts.clean_drafts(before)
        return {"kind": kind, "before": before, **result}
    if kind == "nonces":
        deleted = service.state.clean_nonces(before)
        service.state.audit(
            "clean.records",
            kind,
            {"kind": kind, "before": before, "deleted": deleted},
        )
        service.state.checkpoint()
        return {"kind": kind, "before": before, "deleted": deleted}
    if kind == "approvals":
        deleted = service.state.clean_approvals(before)
        service.state.audit(
            "clean.records",
            kind,
            {"kind": kind, "before": before, "deleted": deleted},
        )
        service.state.checkpoint()
        return {"kind": kind, "before": before, "deleted": deleted}
    if kind == "audit":
        deleted = service.state.clean_audit(before)
    else:
        deleted = service.state.clean_idempotency(before)
    service.state.audit(
        "clean.records",
        kind,
        {"kind": kind, "before": before, "deleted": deleted},
    )
    return {"kind": kind, "before": before, "deleted": deleted}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "serve":
        configure_logging()
        from .server import run_stdio

        run_stdio(Settings.from_env())
        return 0
    configure_logging()
    try:
        settings = Settings.from_env()
        if arguments.command == "doctor":
            from .doctor import doctor_report

            result = doctor_report(settings)
        elif arguments.command == "install-backtrader":
            from .backtrader_runtime import ensure_cloudquant_backtrader

            result = ensure_cloudquant_backtrader()
        else:
            service = BacktraderMCPService(settings)
        if arguments.command == "approve":
            if arguments.change_set and not arguments.change_token:
                parser.error("--change-token is required with --change-set")
            if arguments.run_plan and not arguments.run_token:
                parser.error("--run-token is required with --run-plan")
            subject_id = arguments.change_set or arguments.run_plan
            if not arguments.yes:
                if not sys.stdin.isatty():
                    parser.error("--yes is required when stdin is not a TTY")
                answer = input(f"Type the full subject id {subject_id!r} to approve exact hashes: ")
                if answer != subject_id:
                    print("approval cancelled", file=sys.stderr)
                    return 2
            if arguments.change_set:
                result = service.changes.approve_change(
                    arguments.change_set, arguments.change_token
                )
            else:
                result = service.jobs.approve_run_plan(arguments.run_plan, arguments.run_token)
        elif arguments.command == "audit-independence":
            result = service.audit_independence()
        elif arguments.command == "recover":
            result = service.recovery
        elif arguments.command == "list":
            result = _list_objects(service, arguments.kind, arguments.state, arguments.limit)
        elif arguments.command == "show":
            result = _show_object(service, arguments.kind, arguments.id)
        elif arguments.command == "clean":
            result = _clean_records(service, arguments.kind, arguments.before)
        elif arguments.command == "logs":
            return _print_job_logs(service, arguments.job)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
        return 0 if result.get("status", "passed") != "failed" else 1
    except ProductError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
