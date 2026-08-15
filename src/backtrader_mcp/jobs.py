"""Durable product-owned asynchronous job API."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .backtrader_runtime import require_cloudquant_runtime
from .data import DatasetService
from .drafts import DraftService
from .errors import Conflict, InvalidRequest, NotFound, sanitize_for_client
from .locks import LockManager
from .logging_config import get_logger
from .process_control import is_posix, platform_environment, popen_group_options, terminate_pid
from .security import TokenSigner
from .settings import Settings
from .state import StateStore
from .util import file_hash, sha256_json, utc_now

logger = get_logger("jobs")

TERMINAL_STATES = {"CANCELLED", "SUCCEEDED", "FAILED", "TIMED_OUT", "ORPHANED"}
ACTIVE_STATES = {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
RUN_PROFILE_MODES = {
    "runonce": ("runonce",),
    "runnext": ("runnext",),
    "runonce_runnext_compare": ("runonce", "runnext"),
    "fixed_tests": ("runonce", "runnext"),
}
RUN_PROFILES = set(RUN_PROFILE_MODES)
JOB_ID_PATTERN = re.compile(r"^job_[0-9a-f]{32}$")
DEFAULT_LOG_TAIL_BYTES = 8000
MAX_LOG_TAIL_BYTES = 25000
WATCHDOG_INTERVAL_SECONDS = 2.0
HEARTBEAT_STALE_SECONDS = 15.0
WATCHDOG_DEADLINE_GRACE_SECONDS = 5.0


def job_summary(job: dict[str, Any]) -> dict[str, Any]:
    """Project a durable job payload into the stable list summary shape."""
    error = job.get("error") or ""
    return {
        "job_id": job.get("job_id"),
        "state": job.get("state"),
        "draft_id": job.get("draft_id"),
        "run_profile_id": job.get("run_profile_id"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": error[:200],
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _elapsed_seconds(job: dict[str, Any]) -> float | None:
    created = _parse_iso(job.get("created_at"))
    if created is None:
        return None
    finished = _parse_iso(job.get("finished_at"))
    end = finished if finished is not None else datetime.now(timezone.utc)
    return round(max(0.0, (end - created).total_seconds()), 3)


def _eta_bound(job: dict[str, Any]) -> str | None:
    if job.get("state") not in ACTIVE_STATES:
        return None
    started = _parse_iso(job.get("started_at"))
    timeout = job.get("timeout_seconds")
    if started is None or not isinstance(timeout, (int, float)) or timeout <= 0:
        return None
    return (started + timedelta(seconds=timeout)).isoformat()


def _tail_bytes(path: Path, limit: int) -> str:
    """Read the last ``limit`` bytes of a file without loading it fully.

    Bounded-read trade-offs: if the file grows between the size checks the
    returned content can exceed ``limit`` while ``truncated`` stays false, and
    a byte-boundary cut can split one multi-byte UTF-8 character (replaced
    with U+FFFD). Both are acceptable for diagnostic tails.
    """
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - limit))
        return stream.read().decode("utf-8", errors="replace")


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid < 2:
        return False
    if not is_posix():
        # On Windows os.kill(pid, 0) is not a harmless liveness probe; any
        # non-console signal can terminate the process. Cancellation itself is
        # idempotent, so request it for a structurally valid recorded PID.
        return True
    try:
        waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class JobService:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        locks: LockManager,
        drafts: DraftService,
        datasets: DatasetService,
        signer: TokenSigner,
    ):
        self.settings = settings
        self.state = state
        self.locks = locks
        self.drafts = drafts
        self.datasets = datasets
        self.signer = signer

    def prepare_strategy_run(
        self,
        draft_id: str,
        validation_token: str,
        dataset_id: str,
        runtime_id: str,
        timeout_seconds: int,
        run_profile_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds < 1
            or timeout_seconds > self.settings.max_run_seconds
        ):
            raise InvalidRequest(
                f"timeout_seconds must be between 1 and {self.settings.max_run_seconds}"
            )
        if run_profile_id not in RUN_PROFILES:
            raise InvalidRequest("run_profile_id is not a fixed P0 profile")
        request = {
            "draft_id": draft_id,
            "validation_token_hash": sha256_json(validation_token),
            "dataset_id": dataset_id,
            "runtime_id": runtime_id,
            "timeout_seconds": timeout_seconds,
            "run_profile_id": run_profile_id,
        }
        prior = self.state.idempotent_get("prepare_strategy_run", idempotency_key, request)
        if prior is not None:
            return prior
        verified = self.drafts.verify_validation(draft_id, validation_token)
        declared_run_modes = verified["draft"]["strategy_spec"]["run_modes"]
        execution_modes = list(RUN_PROFILE_MODES[run_profile_id])
        missing_modes = [mode for mode in execution_modes if mode not in declared_run_modes]
        if missing_modes:
            raise InvalidRequest(
                "run_profile_id requires StrategySpec run_modes to include: "
                f"{', '.join(missing_modes)}"
            )
        dataset = self.datasets.get_dataset(dataset_id)
        if verified["draft"]["strategy_spec"]["dataset_id"] != dataset_id:
            raise Conflict("run dataset does not match the canonical StrategySpec dataset_id")
        runtime = self.settings.runtimes.get(runtime_id)
        if runtime is None:
            raise NotFound(f"Backtrader runtime not registered: {runtime_id}")
        runtime = require_cloudquant_runtime(runtime)
        run_plan_id = f"runplan_{uuid.uuid4().hex}"
        plan_binding = {
            "run_plan_id": run_plan_id,
            "draft_id": draft_id,
            "draft_revision": verified["draft"]["revision"],
            "draft_manifest_hash": verified["draft"]["manifest_hash"],
            "artifact_hash": verified["draft"]["artifact_manifest"]["artifact_hash"],
            "validation_id": verified["validation"]["validation_id"],
            "validation_hash": verified["validation"]["validation_hash"],
            "dataset_id": dataset_id,
            "dataset_semantic_hash": dataset["semantic_hash"],
            "dataset_content_hashes": {
                name: item["sha256"]
                for name, item in sorted(dataset["extensions"]["feed_objects"].items())
            },
            "runtime_id": runtime_id,
            "runtime_version_file_hash": file_hash(runtime / "backtrader" / "version.py"),
            "timeout_seconds": timeout_seconds,
            "run_profile_id": run_profile_id,
            "run_modes": declared_run_modes,
            "execution_modes": execution_modes,
            "output_profile": verified["draft"]["profile"],
        }
        run_plan_hash = sha256_json(plan_binding)
        run_token = self.signer.issue(
            "run_plan",
            {"run_plan_id": run_plan_id, "run_plan_hash": run_plan_hash},
            ttl_seconds=1800,
        )
        plan = {
            **plan_binding,
            "run_plan_hash": run_plan_hash,
            "status": "prepared",
            "created_at": utc_now(),
        }
        self.state.put("run_plan", run_plan_id, plan)
        response = {
            "run_plan_id": run_plan_id,
            "run_token": run_token,
            "run_plan_hash": run_plan_hash,
            "frozen_inputs": plan_binding,
            "approval_command": f"backtrader-mcp approve --run-plan {run_plan_id} "
            f"--run-token '{run_token}'",
        }
        self.state.idempotent_put("prepare_strategy_run", idempotency_key, request, response)
        self.state.audit("run_plan.prepared", run_plan_id, {"run_plan_hash": run_plan_hash})
        return response

    def approve_run_plan(self, run_plan_id: str, run_token: str) -> dict[str, Any]:
        claims = self.signer.verify(run_token, "run_plan")
        plan = self.state.get("run_plan", run_plan_id)
        if (
            claims.get("run_plan_id") != run_plan_id
            or claims.get("run_plan_hash") != plan["run_plan_hash"]
            or plan["status"] != "prepared"
        ):
            raise Conflict("run token does not bind the prepared run plan")
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        return self.state.create_approval(
            "run",
            run_plan_id,
            plan["run_plan_hash"],
            expires.isoformat(),
        )

    def _assert_capacity(self) -> None:
        """Reject new starts when the active-job cap is reached (no queueing)."""
        active_count = sum(
            1 for existing in self.state.list("job") if existing.get("state") in ACTIVE_STATES
        )
        if active_count >= self.settings.max_concurrent_jobs:
            raise Conflict(
                "too many concurrent jobs; the product rejects instead of queueing",
                suggestion=(
                    "use list_jobs with state='active' to find running jobs, then "
                    "cancel one or wait for it to finish"
                ),
            )

    def _create_job_record(
        self, plan: dict[str, Any], runtime: Path, approval_id: str
    ) -> tuple[str, Path]:
        """Create the durable QUEUED job row and mark the run plan started.

        Called while holding both the per-plan and the global concurrency
        locks, so the active-job count and the job row are atomic. Returns
        the new job ID and its private job directory.
        """
        job_id = f"job_{uuid.uuid4().hex}"
        job_root = self.settings.state_root / "jobs" / job_id
        job_root.mkdir(mode=0o700)
        entrypoint = "test_strategy.py" if plan["output_profile"] == "single_test" else "run.py"
        run_manifest_core = {
            "schema_version": "run-manifest-v1",
            "run_id": job_id,
            "artifact_hash": plan["artifact_hash"],
            "dataset_id": plan["dataset_id"],
            "engine": {
                "id": plan["runtime_id"],
                "version_file_hash": plan["runtime_version_file_hash"],
            },
            "environment_hash": sha256_json(
                {
                    "python": sys.version,
                    "runtime_id": plan["runtime_id"],
                    "runtime_version_file_hash": plan["runtime_version_file_hash"],
                }
            ),
            "run_profile": {
                "timeout_seconds": plan["timeout_seconds"],
                "run_modes": plan["run_modes"],
                "execution_modes": plan["execution_modes"],
                "profile_id": plan["run_profile_id"],
            },
            "approval_id": approval_id,
        }
        run_manifest = {
            **run_manifest_core,
            "manifest_hash": sha256_json(run_manifest_core),
        }
        job = {
            "job_id": job_id,
            "state": "QUEUED",
            "run_plan_id": plan["run_plan_id"],
            "draft_id": plan["draft_id"],
            "draft_revision": plan["draft_revision"],
            "draft_manifest_hash": plan["draft_manifest_hash"],
            "validation_id": plan["validation_id"],
            "dataset_id": plan["dataset_id"],
            "dataset_semantic_hash": plan["dataset_semantic_hash"],
            "dataset_content_hashes": plan["dataset_content_hashes"],
            "runtime_id": plan["runtime_id"],
            "runtime_root": str(runtime),
            "entrypoint": entrypoint,
            "timeout_seconds": plan["timeout_seconds"],
            "run_profile_id": plan["run_profile_id"],
            "execution_modes": plan["execution_modes"],
            "resource_limits": self.settings.resource_limits(),
            "worker_pid": None,
            "child_pid": None,
            "created_at": utc_now(),
            "started_at": None,
            "finished_at": None,
            "heartbeat_at": None,
            "error": None,
            "error_kind": None,
            "result": None,
            "run_manifest": run_manifest,
        }
        self.state.put("job", job_id, job)
        self.state.update(
            "run_plan",
            plan["run_plan_id"],
            lambda current_plan: {
                **current_plan,
                "status": "started",
                "job_id": job_id,
                "approval_id": approval_id,
            },
        )
        return job_id, job_root

    def start_strategy_run(
        self,
        run_plan_id: str,
        run_token: str,
        approval_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = {
            "run_plan_id": run_plan_id,
            "run_token_hash": sha256_json(run_token),
            "approval_id": approval_id,
        }
        prior = self.state.idempotent_get("start_strategy_run", idempotency_key, request)
        if prior is not None:
            return prior
        claims = self.signer.verify(run_token, "run_plan")
        with self.locks.acquire(f"run-plan:{run_plan_id}"):
            plan = self.state.get("run_plan", run_plan_id)
            if (
                claims.get("run_plan_id") != run_plan_id
                or claims.get("run_plan_hash") != plan["run_plan_hash"]
                or plan["status"] != "prepared"
            ):
                raise Conflict("run token is stale or does not bind this run plan")
            with self.locks.acquire("job-concurrency"):
                # Recheck idempotency under the global lock so a key reused
                # across two run plans cannot create a duplicate job.
                prior = self.state.idempotent_get("start_strategy_run", idempotency_key, request)
                if prior is not None:
                    return prior
                draft = self.drafts.get_draft(plan["draft_id"])
                dataset = self.datasets.get_dataset(plan["dataset_id"])
                runtime = self.settings.runtimes.get(plan["runtime_id"])
                if runtime is None:
                    raise NotFound(f"Backtrader runtime not registered: {plan['runtime_id']}")
                runtime = require_cloudquant_runtime(runtime)
                current = {
                    "draft_revision": draft["revision"],
                    "draft_manifest_hash": draft["manifest_hash"],
                    "artifact_hash": draft["artifact_manifest"]["artifact_hash"],
                    "dataset_semantic_hash": dataset["semantic_hash"],
                    "dataset_content_hashes": {
                        name: item["sha256"]
                        for name, item in sorted(dataset["extensions"]["feed_objects"].items())
                    },
                    "runtime_version_file_hash": file_hash(runtime / "backtrader" / "version.py"),
                }
                if any(plan[key] != value for key, value in current.items()):
                    raise Conflict("run inputs changed after prepare")
                self._assert_capacity()
                self.state.consume_approval(approval_id, "run", run_plan_id, plan["run_plan_hash"])
                job_id, job_root = self._create_job_record(plan, runtime, approval_id)
        package_src = str(Path(__file__).resolve().parents[1])
        environment = platform_environment(
            {
                "PATH": os.environ.get("PATH", ""),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
                "PYTHONPATH": os.pathsep.join([package_src, str(runtime)]),
                "BACKTRADER_MCP_LOG_LEVEL": os.environ.get("BACKTRADER_MCP_LOG_LEVEL", "WARNING"),
            }
        )
        supervisor_stdout = (job_root / "supervisor.stdout.log").open("ab")
        supervisor_stderr = (job_root / "supervisor.stderr.log").open("ab")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "backtrader_mcp.worker",
                    "--state-root",
                    str(self.settings.state_root),
                    "--job-id",
                    job_id,
                ],
                cwd=job_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=supervisor_stdout,
                stderr=supervisor_stderr,
                close_fds=True,
                **popen_group_options(),
            )
        except OSError as exc:
            error_message = f"worker launch failed: {exc}"
            self.state.update(
                "job",
                job_id,
                lambda current: {
                    **current,
                    "state": "FAILED",
                    "finished_at": utc_now(),
                    "error": error_message,
                },
            )
            raise InvalidRequest("could not launch the controlled worker") from exc
        finally:
            supervisor_stdout.close()
            supervisor_stderr.close()
        self.state.update("job", job_id, lambda current: {**current, "worker_pid": process.pid})
        logger.info("job.started job_id=%s worker_pid=%s", job_id, process.pid)
        response = {
            "job_id": job_id,
            "run_id": job_id,
            "state": "QUEUED",
            "status_uri": f"backtrader-mcp://jobs/{job_id}",
            "result_uri": f"backtrader-mcp://jobs/{job_id}/result",
        }
        self.state.idempotent_put("start_strategy_run", idempotency_key, request, response)
        self.state.audit("job.started", job_id, response)
        return response

    def get_run_status(self, job_id: str) -> dict[str, Any]:
        with self.locks.acquire(f"job:{job_id}"):
            job = self.state.get("job", job_id)
            if job["state"] in ACTIVE_STATES and not _pid_alive(job.get("worker_pid")):
                try:
                    job = self.state.update(
                        "job",
                        job_id,
                        lambda current: {
                            **current,
                            "state": "ORPHANED",
                            "finished_at": utc_now(),
                            "error": "worker process disappeared before a terminal state was persisted",
                            "error_kind": "orphaned",
                        },
                        expected=lambda current: current.get("state") in ACTIVE_STATES,
                    )
                    logger.warning("job.orphaned job_id=%s", job_id)
                except Conflict:
                    # Another actor (worker or watchdog) finalized the job first;
                    # report the persisted state instead of overwriting it.
                    job = self.state.get("job", job_id)
            status = {key: value for key, value in job.items() if key not in {"runtime_root"}}
            status["log_uri"] = f"backtrader-mcp://jobs/{job_id}/logs"
            status["elapsed_seconds"] = _elapsed_seconds(job)
            status["eta_bound"] = _eta_bound(job)
            return status

    def list_jobs(
        self, state_filter: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        valid_states = sorted(TERMINAL_STATES | ACTIVE_STATES | {"active"})
        if state_filter is not None and state_filter not in valid_states:
            raise InvalidRequest(
                f"unknown job state: {state_filter}; valid states: {', '.join(valid_states)}"
            )
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise InvalidRequest("job list limit must be between 1 and 100")
        if not isinstance(offset, int) or offset < 0:
            raise InvalidRequest("job list offset must be a non-negative integer")
        jobs = sorted(
            self.state.list("job"),
            key=lambda job: job.get("created_at", ""),
            reverse=True,
        )
        if state_filter == "active":
            jobs = [job for job in jobs if job.get("state") in ACTIVE_STATES]
        elif state_filter is not None:
            jobs = [job for job in jobs if job.get("state") == state_filter]
        total = len(jobs)
        page = jobs[offset : offset + limit]
        return {
            "schema_version": "job-list-v1",
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
            "jobs": [job_summary(job) for job in page],
        }

    def get_job_logs(self, job_id: str, tail_bytes: int = DEFAULT_LOG_TAIL_BYTES) -> dict[str, Any]:
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.match(job_id):
            raise InvalidRequest(
                "job_id must match the job_<32 hex characters> format",
                suggestion="use list_jobs to discover valid job IDs",
            )
        if not isinstance(tail_bytes, int) or tail_bytes < 1 or tail_bytes > MAX_LOG_TAIL_BYTES:
            raise InvalidRequest(f"tail_bytes must be between 1 and {MAX_LOG_TAIL_BYTES}")
        try:
            job = self.state.get("job", job_id)
        except NotFound:
            raise NotFound(
                f"job not found: {job_id}",
                suggestion="use list_jobs to discover existing job IDs",
            ) from None
        job_root = self.settings.state_root / "jobs" / job_id
        files: dict[str, dict[str, Any]] = {}
        for path in sorted(job_root.glob("*.log")):
            if not path.is_file():
                continue
            size = path.stat().st_size
            files[path.name] = {
                "size_bytes": size,
                "truncated": size > tail_bytes,
                "content": sanitize_for_client(_tail_bytes(path, tail_bytes)),
            }
        return {
            "schema_version": "job-logs-v1",
            "job_id": job_id,
            "state": job["state"],
            "tail_bytes": tail_bytes,
            "files": files,
        }

    def cancel_strategy_run(self, job_id: str, idempotency_key: str) -> dict[str, Any]:
        request = {"job_id": job_id}
        prior = self.state.idempotent_get("cancel_strategy_run", idempotency_key, request)
        if prior is not None:
            return prior
        with self.locks.acquire(f"job:{job_id}"):
            job = self.state.get("job", job_id)
            if job["state"] in TERMINAL_STATES:
                response = {"job_id": job_id, "state": job["state"], "already_terminal": True}
            else:
                try:
                    self.state.update(
                        "job",
                        job_id,
                        lambda current: {
                            **current,
                            "state": "CANCEL_REQUESTED",
                            "error": "cancel requested by local client",
                            "error_kind": "cancelled",
                        },
                        expected=lambda current: current.get("state") in ACTIVE_STATES,
                    )
                except Conflict:
                    # A terminal state was persisted concurrently; honor it.
                    final = self.state.get("job", job_id)
                    response = {
                        "job_id": job_id,
                        "state": final["state"],
                        "already_terminal": True,
                    }
                    self.state.idempotent_put(
                        "cancel_strategy_run", idempotency_key, request, response
                    )
                    return response
                child_pid = job.get("child_pid")
                worker_pid = job.get("worker_pid")
                for pid in (child_pid, worker_pid):
                    if isinstance(pid, int) and not isinstance(pid, bool) and _pid_alive(pid):
                        terminate_pid(pid)
                try:
                    self.state.update(
                        "job",
                        job_id,
                        lambda current: {
                            **current,
                            "state": "CANCELLED",
                            "finished_at": utc_now(),
                            "error": "cancelled by local client request",
                            "error_kind": "cancelled",
                        },
                        expected=lambda current: current.get("state") == "CANCEL_REQUESTED",
                    )
                except Conflict:
                    # The worker or watchdog finalized first; report its state.
                    pass
                final = self.state.get("job", job_id)
                response = {
                    "job_id": job_id,
                    "state": final["state"],
                    "already_terminal": final["state"] in TERMINAL_STATES,
                }
            self.state.idempotent_put("cancel_strategy_run", idempotency_key, request, response)
            self.state.audit("job.cancelled", job_id, response)
            logger.info("job.cancelled job_id=%s", job_id)
            return response

    def get_run_result(self, job_id: str) -> dict[str, Any]:
        job = self.get_run_status(job_id)
        if job["state"] != "SUCCEEDED" or not isinstance(job.get("result"), dict):
            raise Conflict(
                f"job has no successful result: {job['state']}",
                suggestion="use get_run_logs to inspect the failure logs",
            )
        return job["result"]

    def recover_jobs(self) -> list[str]:
        recovered: list[str] = []
        for job in self.state.list("job"):
            if job["state"] in ACTIVE_STATES and not _pid_alive(job.get("worker_pid")):
                try:
                    self.state.update(
                        "job",
                        job["job_id"],
                        lambda current: {
                            **current,
                            "state": "ORPHANED",
                            "finished_at": utc_now(),
                            "error": "worker was absent during startup recovery",
                            "error_kind": "orphaned",
                        },
                        expected=lambda current: current.get("state") in ACTIVE_STATES,
                    )
                except Conflict:
                    continue
                recovered.append(job["job_id"])
                logger.info("job.recovered job_id=%s", job["job_id"])
        return recovered

    # ------------------------------------------------------------------
    # Supervision, retention, and diagnostics
    # ------------------------------------------------------------------

    def _watchdog_decision(self, job: dict[str, Any]) -> str | None:
        """Decide one enforcement action for an ACTIVE job, or None."""
        worker_pid = job.get("worker_pid")
        if not _pid_alive(worker_pid):
            return "orphan"
        started = _parse_iso(job.get("started_at"))
        timeout = job.get("timeout_seconds")
        if started is not None and isinstance(timeout, (int, float)) and timeout > 0:
            deadline = started + timedelta(seconds=timeout + WATCHDOG_DEADLINE_GRACE_SECONDS)
            if datetime.now(timezone.utc) > deadline:
                return "timeout"
        heartbeat = _parse_iso(job.get("heartbeat_at"))
        if heartbeat is None:
            return None
        stale_after = heartbeat + timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        if datetime.now(timezone.utc) > stale_after:
            return "timeout"
        return None

    def _enforce_watchdog_decision(self, job: dict[str, Any], decision: str) -> None:
        """Kill leftover processes first, then persist the terminal state via CAS."""
        job_id = job["job_id"]
        child_pid = job.get("child_pid")
        worker_pid = job.get("worker_pid")
        if decision == "timeout":
            for pid in (child_pid, worker_pid):
                if isinstance(pid, int) and not isinstance(pid, bool) and _pid_alive(pid):
                    terminate_pid(pid)
            try:
                self.state.update(
                    "job",
                    job_id,
                    lambda current: {
                        **current,
                        "state": "TIMED_OUT",
                        "finished_at": utc_now(),
                        "error": "watchdog: worker heartbeat lost or wall-clock deadline exceeded",
                        "error_kind": "timeout",
                    },
                    expected=lambda current: current.get("state") in ACTIVE_STATES,
                )
            except Conflict:
                pass
            return
        if isinstance(child_pid, int) and not isinstance(child_pid, bool):
            # The worker is gone but its detached candidate session may survive;
            # terminate_pid is a harmless no-op when the group is already dead.
            terminate_pid(child_pid)
        try:
            self.state.update(
                "job",
                job_id,
                lambda current: {
                    **current,
                    "state": "ORPHANED",
                    "finished_at": utc_now(),
                    "error": "watchdog: worker process disappeared before a terminal state",
                    "error_kind": "orphaned",
                },
                expected=lambda current: current.get("state") in ACTIVE_STATES,
            )
        except Conflict:
            pass

    def watchdog_tick(self) -> dict[str, Any]:
        """One supervision pass over ACTIVE jobs (idempotent, CAS-guarded)."""
        enforced: list[dict[str, str]] = []
        for job in self.state.list("job"):
            if job.get("state") not in ACTIVE_STATES:
                continue
            job_id = job["job_id"]
            with self.locks.acquire(f"job:{job_id}"):
                current = self.state.maybe_get("job", job_id)
                if current is None or current.get("state") not in ACTIVE_STATES:
                    continue
                decision = self._watchdog_decision(current)
                if decision is None:
                    continue
                self._enforce_watchdog_decision(current, decision)
                enforced.append({"job_id": job_id, "decision": decision})
                logger.warning("watchdog.enforced job_id=%s decision=%s", job_id, decision)
        return {"enforced": enforced}

    def start_watchdog(self) -> "JobWatchdog":
        return JobWatchdog(self).start()

    def clean_jobs(self, before_iso: str) -> dict[str, int]:
        """Delete terminal jobs finished before ``before_iso`` (rows and dirs)."""
        removed_dirs = 0
        deleted_rows = 0
        for job in self.state.list("job"):
            if job.get("state") not in TERMINAL_STATES:
                continue
            finished = job.get("finished_at")
            if not finished or finished >= before_iso:
                continue
            job_id = job["job_id"]
            job_root = self.settings.state_root / "jobs" / job_id
            if job_root.is_dir():
                shutil.rmtree(job_root, ignore_errors=True)
                removed_dirs += 1
            self.state.delete("job", job_id)
            deleted_rows += 1
            logger.info("job.cleaned job_id=%s", job_id)
        self.state.audit(
            "clean.jobs",
            None,
            {"before": before_iso, "deleted_rows": deleted_rows, "removed_dirs": removed_dirs},
        )
        self.state.checkpoint()
        return {"deleted_rows": deleted_rows, "removed_dirs": removed_dirs}


class JobWatchdog:
    """Daemon supervision loop owned by the serving process only."""

    def __init__(self, jobs: JobService, interval_seconds: float = WATCHDOG_INTERVAL_SECONDS):
        self.jobs = jobs
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "JobWatchdog":
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._loop, name="backtrader-mcp-watchdog", daemon=True
            )
            self._thread.start()
            logger.info("watchdog.started interval=%.1f", self.interval)
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        logger.info("watchdog.stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.jobs.watchdog_tick()
            except Exception:
                logger.exception("watchdog.tick_failed")
