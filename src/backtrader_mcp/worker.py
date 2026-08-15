"""Controlled worker process; the MCP server never imports candidate modules."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .errors import Conflict, InvalidRequest
from .jobs import ACTIVE_STATES, RUN_PROFILE_MODES, TERMINAL_STATES
from .logging_config import configure_logging, get_logger
from .process_control import platform_environment, popen_group_options, terminate_popen
from .reports import compare_metrics, normalize_metrics, render_markdown
from .state import StateStore
from .util import atomic_write, file_hash, sha256_json, utc_now

resource_module: Any | None
try:
    import resource as _resource_module
except ImportError:  # Windows lacks the resource module
    resource_module = None
else:
    resource_module = _resource_module

logger = get_logger("worker")

# Candidate processes are intentionally capped to a small process budget.  Common
# numerical libraries otherwise try to create a CPU-sized thread pool during
# import, which both weakens that budget and can make a constrained worker fail
# before it executes user code.
_NUMERIC_THREAD_ENVIRONMENT = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
}


def _apply_resource_limits(limits: dict[str, int]) -> None:
    """Apply candidate subprocess resource caps in the child before exec.

    Runs as ``preexec_fn`` so the limits take effect for the candidate process
    only, not the trusted supervisor. Best-effort: unsupported limits or values
    a platform rejects are skipped rather than fatal.
    """
    if resource_module is None:
        return
    spec: list[tuple[int, tuple[int, int]]] = []
    cpu = limits.get("cpu_seconds", 0)
    if cpu and hasattr(resource_module, "RLIMIT_CPU"):
        spec.append((resource_module.RLIMIT_CPU, (cpu, cpu)))
    mem = limits.get("memory_bytes", 0)
    if mem and hasattr(resource_module, "RLIMIT_AS"):
        spec.append((resource_module.RLIMIT_AS, (mem, mem)))
    fsize = limits.get("file_size_bytes", 0)
    if fsize and hasattr(resource_module, "RLIMIT_FSIZE"):
        spec.append((resource_module.RLIMIT_FSIZE, (fsize, fsize)))
    nproc = limits.get("processes", 0)
    if nproc and hasattr(resource_module, "RLIMIT_NPROC"):
        spec.append((resource_module.RLIMIT_NPROC, (nproc, nproc)))
    for res, (soft, hard) in spec:
        try:
            resource_module.setrlimit(res, (soft, hard))
        except (ValueError, OSError):
            pass


def _update_if(store: StateStore, job_id: str, expected: Any, **values: Any) -> dict[str, Any]:
    """Apply values only while ``expected(current)`` holds (CAS write)."""
    return store.update("job", job_id, lambda current: {**current, **values}, expected=expected)


def _write_terminal(
    store: StateStore,
    job_id: str,
    state: str,
    error: str | None,
    error_kind: str | None,
    **extra: Any,
) -> dict[str, Any] | None:
    """Persist a non-cancel terminal state; never overwrites an existing
    terminal state or a visible CANCEL_REQUESTED (arbitration rule)."""

    def precondition(current: dict[str, Any]) -> bool:
        return current.get("state") not in TERMINAL_STATES and current.get("state") != (
            "CANCEL_REQUESTED"
        )

    try:
        return _update_if(
            store,
            job_id,
            precondition,
            state=state,
            finished_at=utc_now(),
            heartbeat_at=utc_now(),
            error=error,
            error_kind=error_kind,
            **extra,
        )
    except Conflict:
        return None


def _write_cancelled(store: StateStore, job_id: str, error: str) -> dict[str, Any] | None:
    """Persist CANCELLED; only valid from CANCEL_REQUESTED (cancel wins once visible)."""
    try:
        return _update_if(
            store,
            job_id,
            lambda current: current.get("state") == "CANCEL_REQUESTED",
            state="CANCELLED",
            finished_at=utc_now(),
            heartbeat_at=utc_now(),
            error=error,
            error_kind="cancelled",
        )
    except Conflict:
        return None


def _write_running(store: StateStore, job_id: str) -> dict[str, Any] | None:
    """Start the run only if the job is still QUEUED."""
    try:
        return _update_if(
            store,
            job_id,
            lambda current: current.get("state") == "QUEUED",
            state="RUNNING",
            started_at=utc_now(),
            heartbeat_at=utc_now(),
            worker_pid=os.getpid(),
        )
    except Conflict:
        return None


def _heartbeat(store: StateStore, job_id: str) -> None:
    """Refresh the liveness heartbeat only while the job stays active."""
    try:
        _update_if(
            store,
            job_id,
            lambda current: current.get("state") in ACTIVE_STATES,
            heartbeat_at=utc_now(),
        )
    except Conflict:
        pass


def _classify_exit(returncode: int) -> tuple[str, str] | None:
    """Classify a candidate exit code into the product error_kind taxonomy."""
    if returncode == 0:
        return None
    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = str(-returncode)
        return "resource_limit", f"candidate was killed by signal {name}"
    return "user_strategy", f"candidate exited {returncode}"


def _validate_result(value: Any, expected_feed_configs: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != "run-result-v1":
        raise ValueError("candidate result does not implement run-result-v1")
    mode = value.get("run_mode")
    if mode not in {"runonce", "runnext"}:
        raise ValueError("candidate result run_mode is invalid")
    try:
        metrics = normalize_metrics(value.get("metrics"))
        extra = metrics.pop("_extra_metrics", None)
    except InvalidRequest as exc:
        raise ValueError(str(exc)) from exc
    evidence = value.get("feed_runtime")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("candidate result has no typed feed runtime evidence")
    expected = {item["name"]: item for item in expected_feed_configs}
    sanitized: list[dict[str, Any]] = []
    strategy_names: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("typed feed runtime evidence must contain objects")
        dataset_feed = item.get("dataset_feed")
        strategy_feed = item.get("strategy_feed")
        config = expected.get(dataset_feed)
        if config is None or not isinstance(strategy_feed, str) or not strategy_feed:
            raise ValueError("typed feed runtime evidence names an unknown feed")
        if strategy_feed in strategy_names:
            raise ValueError("typed feed runtime evidence repeats a strategy feed")
        strategy_names.add(strategy_feed)
        if (
            item.get("input_format") != config["input_format"]
            or item.get("adapter") != config["adapter"]
            or item.get("bar_operation") != config["bar_operation"]
        ):
            raise ValueError("typed feed runtime evidence does not match the frozen DataSpec")
        source_rows = item.get("source_row_count")
        output_bars = item.get("output_bar_count")
        if (
            not isinstance(source_rows, int)
            or isinstance(source_rows, bool)
            or source_rows < 1
            or not isinstance(output_bars, int)
            or isinstance(output_bars, bool)
            or output_bars < 1
        ):
            raise ValueError("typed feed runtime evidence has invalid row counts")
        constructed = item.get("constructed_class")
        registered = item.get("registered_class")
        if not isinstance(constructed, str) or not constructed or not isinstance(registered, str):
            raise ValueError("typed feed runtime evidence has invalid adapter classes")
        sanitized.append(
            {
                "dataset_feed": dataset_feed,
                "strategy_feed": strategy_feed,
                "input_format": config["input_format"],
                "adapter": config["adapter"],
                "constructed_class": constructed,
                "registered_class": registered,
                "bar_operation": config["bar_operation"],
                "source_row_count": source_rows,
                "output_bar_count": output_bars,
            }
        )
    return {
        "schema_version": "run-result-v1",
        "run_mode": mode,
        "metrics": metrics,
        "feed_runtime": sanitized,
        "extra_metrics": extra,
    }


def _candidate_environment(
    *,
    runtime_root: str,
    package_src: str,
    master_dataset_path: str,
    dataset_paths: dict[str, str],
    feed_configs: list[dict[str, Any]],
    result_path: str | Path,
    mode: str,
) -> dict[str, str]:
    """Return the deliberately small environment granted to a strategy candidate."""

    return platform_environment(
        {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "PYTHONPATH": os.pathsep.join([runtime_root, package_src]),
            # The required CloudQuant runtime supports this core-only import mode.
            # It excludes optional plotting/analysis integrations from every isolated
            # candidate process without changing the trusted MCP supervisor.
            "BACKTRADER_LIGHT_IMPORT": "1",
            **_NUMERIC_THREAD_ENVIRONMENT,
            "BACKTRADER_MCP_DATASET": master_dataset_path,
            "BACKTRADER_MCP_DATASETS_JSON": json.dumps(
                dataset_paths, sort_keys=True, separators=(",", ":")
            ),
            "BACKTRADER_MCP_FEEDS_JSON": json.dumps(
                feed_configs, sort_keys=True, separators=(",", ":")
            ),
            "BACKTRADER_MCP_RESULT": str(result_path),
            "BACKTRADER_MCP_RUN_MODE": mode,
        }
    )


def run_worker(state_root: Path, job_id: str) -> int:
    state = StateStore(state_root)
    job = state.get("job", job_id)
    job_root = state_root / "jobs" / job_id
    draft = state.get("draft", job["draft_id"])
    dataset = state.get("dataset", job["dataset_id"])
    draft_root = state_root / "drafts" / job["draft_id"]
    feed_objects = dataset["extensions"]["feed_objects"]
    dataset_paths: dict[str, str] = {}
    feed_configs: list[dict[str, Any]] = []
    for feed in dataset["feeds"]:
        name = feed["name"]
        item = feed_objects[name]
        dataset_path = state_root / item["cas_relative_path"]
        if (
            file_hash(dataset_path) != item["sha256"]
            or job["dataset_content_hashes"].get(name) != item["sha256"]
        ):
            _write_terminal(
                state,
                job_id,
                "FAILED",
                f"dataset CAS content failed its hash check: {name}",
                "infrastructure",
            )
            return 2
        dataset_paths[name] = str(dataset_path)
        feed_configs.append(
            {
                "name": name,
                "canonical_csv_path": str(dataset_path),
                "content_sha256": item["sha256"],
                "input_format": item["input_format"],
                "adapter": item["adapter"],
                "source_timeframe": item["source_timeframe"],
                "source_compression": item["source_compression"],
                "custom_lines": item["custom_lines"],
                "bar_operation": item["bar_operation"],
            }
        )
    master_dataset_path = dataset_paths[dataset["master_feed"]]
    for relative, digest in draft["manifest"].items():
        if file_hash(draft_root / relative) != digest:
            _write_terminal(
                state,
                job_id,
                "FAILED",
                "draft content failed its hash check",
                "infrastructure",
            )
            return 2
    entrypoint = draft_root / job["entrypoint"]
    expected_modes = list(RUN_PROFILE_MODES.get(job["run_profile_id"], ()))
    modes = job.get("execution_modes")
    if (
        not isinstance(modes, list)
        or any(mode not in {"runonce", "runnext"} for mode in modes)
        or modes != expected_modes
    ):
        _write_terminal(
            state,
            job_id,
            "FAILED",
            "job execution modes do not match the frozen run profile",
            "validation",
        )
        return 2
    resource_limits = job.get("resource_limits") or {}
    if _write_running(state, job_id) is None:
        logger.info("worker.start_suppressed job_id=%s", job_id)
        return 3
    logger.info("worker.run_start job_id=%s profile=%s", job_id, job["run_profile_id"])
    deadline = time.monotonic() + job["timeout_seconds"]
    mode_results: dict[str, dict[str, Any]] = {}
    extra_metrics: dict[str, Any] | None = None
    candidate_artifacts: list[dict[str, Any]] = []
    package_src = str(Path(__file__).resolve().parents[1])
    for mode in modes:
        result_path = job_root / f"result.{mode}.candidate.json"
        stdout_path = job_root / f"candidate.{mode}.stdout.log"
        stderr_path = job_root / f"candidate.{mode}.stderr.log"
        environment = _candidate_environment(
            runtime_root=job["runtime_root"],
            package_src=package_src,
            master_dataset_path=master_dataset_path,
            dataset_paths=dataset_paths,
            feed_configs=feed_configs,
            result_path=result_path,
            mode=mode,
        )
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                [sys.executable, str(entrypoint)],
                cwd=draft_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                close_fds=True,
                **popen_group_options(preexec_fn=lambda: _apply_resource_limits(resource_limits)),
            )
            recorded = _update_if(
                state,
                job_id,
                lambda current: current.get("state") in ACTIVE_STATES,
                child_pid=process.pid,
                heartbeat_at=utc_now(),
                active_mode=mode,
            )
            if recorded is None:
                terminate_popen(process)
                logger.info("worker.child_record_suppressed job_id=%s", job_id)
                return 3
            last_heartbeat = time.monotonic()
            while process.poll() is None:
                current = state.get("job", job_id)
                if current["state"] == "CANCEL_REQUESTED":
                    terminate_popen(process)
                    _write_cancelled(state, job_id, "cancelled while running")
                    return 3
                now = time.monotonic()
                if now >= deadline:
                    terminate_popen(process)
                    _write_terminal(
                        state,
                        job_id,
                        "TIMED_OUT",
                        f"run exceeded {job['timeout_seconds']} seconds",
                        "timeout",
                    )
                    return 4
                if now - last_heartbeat >= 1.0:
                    _heartbeat(state, job_id)
                    last_heartbeat = now
                time.sleep(0.2)
        if process.returncode != 0:
            stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            classified = _classify_exit(process.returncode)
            assert classified is not None  # nonzero returncodes always classify
            kind, detail = classified
            error = f"{mode} {detail}" + (f": {stderr_tail}" if stderr_tail else "")
            _write_terminal(state, job_id, "FAILED", error, kind)
            return process.returncode or 1
        try:
            if result_path.stat().st_size > 1024 * 1024:
                raise ValueError("candidate result exceeds 1 MiB")
            candidate = _validate_result(
                json.loads(result_path.read_text(encoding="utf-8")),
                feed_configs,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _write_terminal(
                state,
                job_id,
                "FAILED",
                f"{mode} result validation failed: {exc}",
                "validation",
            )
            return 5
        if candidate.get("extra_metrics"):
            extra_metrics = extra_metrics or {}
            extra_metrics.update(candidate["extra_metrics"])
        mode_results[mode] = candidate
        candidate_artifacts.extend(
            [
                {
                    "role": f"{mode}_candidate_result",
                    "path": result_path.name,
                    "bytes": result_path.stat().st_size,
                    "sha256": file_hash(result_path),
                },
                {
                    "role": f"{mode}_stderr",
                    "path": stderr_path.name,
                    "bytes": stderr_path.stat().st_size,
                    "sha256": file_hash(stderr_path),
                },
            ]
        )
    try:
        primary_mode = "runonce" if "runonce" in mode_results else modes[0]
        comparison = (
            compare_metrics(
                mode_results["runonce"]["metrics"],
                mode_results["runnext"]["metrics"],
            )
            if {"runonce", "runnext"} <= set(mode_results)
            else None
        )
        normalized_path = job_root / "result.json"
        normalized_core = {
            "schema_version": "run-result-v1",
            "run_id": job_id,
            "status": (
                "failed"
                if comparison is not None and comparison["status"] == "mismatched"
                else "passed"
            ),
            "metrics": mode_results[primary_mode]["metrics"],
            "diagnostics": comparison["diagnostics"] if comparison else [],
            "artifacts": candidate_artifacts,
            "extensions": {
                "draft_id": job["draft_id"],
                "draft_revision": job["draft_revision"],
                "artifact_hash": job["run_manifest"]["artifact_hash"],
                "dataset_id": job["dataset_id"],
                "dataset_semantic_hash": job["dataset_semantic_hash"],
                "dataset_content_hashes": job["dataset_content_hashes"],
                "runtime_id": job["runtime_id"],
                "run_manifest_hash": job["run_manifest"]["manifest_hash"],
                "run_profile_id": job["run_profile_id"],
                "mode_results": mode_results,
                "runonce_runnext_comparison": comparison,
                "extra_metrics": extra_metrics,
            },
        }
        normalized = {
            **normalized_core,
            "result_hash": sha256_json(normalized_core),
        }
        report = render_markdown(normalized)
        report_path = job_root / "report.md"
        atomic_write(report_path, report.encode("utf-8"), mode=0o600)
        atomic_write(
            normalized_path,
            json.dumps(normalized, sort_keys=True, default=str).encode("utf-8"),
            mode=0o600,
        )
        result = {
            **normalized,
            "extensions": {
                **normalized["extensions"],
                "result_sha256": file_hash(normalized_path),
                "report_sha256": file_hash(report_path),
                "report_markdown": report,
            },
        }
    except (OSError, ValueError, json.JSONDecodeError, InvalidRequest) as exc:
        _write_terminal(
            state,
            job_id,
            "FAILED",
            f"result validation failed: {exc}",
            "validation",
        )
        return 5
    if _write_terminal(state, job_id, "SUCCEEDED", None, None, result=result) is None:
        logger.info("worker.success_suppressed job_id=%s", job_id)
        return 3
    state.audit(
        "job.succeeded",
        job_id,
        {"result_hash": result["result_hash"]},
    )
    logger.info("worker.run_succeeded job_id=%s", job_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--job-id", required=True)
    arguments = parser.parse_args(argv)
    state_root = Path(arguments.state_root)
    job_id = arguments.job_id
    try:
        return run_worker(state_root, job_id)
    except Exception as exc:
        logger.exception("worker.crashed job_id=%s", job_id)
        try:
            _write_terminal(
                StateStore(state_root),
                job_id,
                "FAILED",
                f"worker crashed: {type(exc).__name__}: {exc}",
                "infrastructure",
            )
        except Exception:
            logger.exception("worker.crash_persistence_failed job_id=%s", job_id)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
