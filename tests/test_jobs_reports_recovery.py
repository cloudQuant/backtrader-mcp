from __future__ import annotations

import os
import signal
import time

import pytest
from conftest import canonical_spec

from backtrader_mcp import worker
from backtrader_mcp.contracts import ARCHETYPES
from backtrader_mcp.service import BacktraderMCPService
from backtrader_mcp.util import utc_now


def _wait(service, job_id: str, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.get_run_status(job_id)
        if status["state"] in {
            "CANCELLED",
            "SUCCEEDED",
            "FAILED",
            "TIMED_OUT",
            "ORPHANED",
        }:
            return status
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not become terminal")


def test_candidate_environment_enables_cloudquant_light_import_and_thread_caps():
    environment = worker._candidate_environment(
        runtime_root="/trusted-backtrader",
        package_src="/trusted-mcp",
        master_dataset_path="/dataset/primary.csv",
        dataset_paths={"primary": "/dataset/primary.csv"},
        feed_configs=[{"name": "primary"}],
        result_path="/result.json",
        mode="runonce",
    )

    assert environment["BACKTRADER_LIGHT_IMPORT"] == "1"
    assert {
        name: environment[name]
        for name in (
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "BLIS_NUM_THREADS",
        )
    } == {
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
    }


@pytest.mark.parametrize("archetype", sorted(ARCHETYPES))
@pytest.mark.parametrize("profile", ["python_bundle", "single_test"])
def test_distinct_run_approval_fixed_profile_and_report(
    registered_dataset,
    archetype: str,
    profile: str,
):
    service, dataset = registered_dataset
    spec = canonical_spec(dataset["dataset_id"], archetype, profile)
    validated_spec = service.validate_strategy_spec(spec)
    assert validated_spec["status"] == "passed"
    draft = service.create_strategy_draft(spec)
    validation = service.validate_strategy_draft(draft["draft_id"], draft["revision"])
    plan = service.prepare_strategy_run(
        draft["draft_id"],
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        20,
        "fixed_tests",
        f"prepare-{archetype}-{profile}",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"],
        plan["run_token"],
        approval["approval_id"],
        f"start-{archetype}-{profile}",
    )
    status = _wait(service, started["job_id"])
    assert status["state"] == "SUCCEEDED", status.get("error")
    result = service.get_run_result(started["job_id"])
    assert result["schema_version"] == "run-result-v1"
    assert set(result["metrics"]) == {
        "bar_num",
        "buy_count",
        "sell_count",
        "win_count",
        "loss_count",
        "trade_num",
        "final_value",
        "sharpe_ratio",
        "annual_return",
        "max_drawdown",
        "return_rate",
    }
    parity = result["extensions"]["runonce_runnext_comparison"]
    assert parity["status"] == "matched", parity
    rendered = service.render_strategy_report(started["job_id"])
    assert "Canonical metrics" in rendered["content"]
    comparison = service.compare_strategy_runs(started["job_id"], started["job_id"])
    assert comparison["status"] == "matched"


def test_single_mode_run_uses_frozen_execution_modes(registered_dataset):
    service, dataset = registered_dataset
    spec = canonical_spec(dataset["dataset_id"], "single_data_indicator", "python_bundle")
    spec["run_modes"] = ["runonce"]
    draft = service.create_strategy_draft(spec)
    validation = service.validate_strategy_draft(draft["draft_id"], draft["revision"])
    plan = service.prepare_strategy_run(
        draft["draft_id"],
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        20,
        "runonce",
        "prepare-single-mode",
    )
    assert plan["frozen_inputs"]["execution_modes"] == ["runonce"]
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"],
        plan["run_token"],
        approval["approval_id"],
        "start-single-mode",
    )

    status = _wait(service, started["job_id"])

    assert status["state"] == "SUCCEEDED", status.get("error")
    job = service.state.get("job", started["job_id"])
    assert job["execution_modes"] == ["runonce"]
    assert job["run_manifest"]["run_profile"]["execution_modes"] == ["runonce"]
    result = service.get_run_result(started["job_id"])
    assert set(result["extensions"]["mode_results"]) == {"runonce"}
    assert result["extensions"]["runonce_runnext_comparison"] is None


def test_cancel_and_restart_recovery(service_env):
    service, _, _ = service_env
    queued = {
        "job_id": "job_" + "1" * 32,
        "state": "QUEUED",
        "worker_pid": None,
        "child_pid": None,
        "created_at": utc_now(),
    }
    service.state.put("job", queued["job_id"], queued)
    cancelled = service.cancel_strategy_run(queued["job_id"], "cancel-1")
    assert cancelled["state"] == "CANCELLED"
    orphan = {
        "job_id": "job_" + "2" * 32,
        "state": "RUNNING",
        "worker_pid": 99999999,
        "child_pid": None,
        "created_at": utc_now(),
    }
    service.state.put("job", orphan["job_id"], orphan)
    recovered = BacktraderMCPService(service.settings)
    assert orphan["job_id"] in recovered.recovery["jobs"]
    assert recovered.get_run_status(orphan["job_id"])["state"] == "ORPHANED"


def _wait_for_state(service, job_id: str, target: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.state.get("job", job_id)
        if job.get("state") == target:
            return job
        if job.get("state") in {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "ORPHANED"}:
            raise AssertionError(f"job reached {job['state']} before {target}")
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not reach {target}")


def _make_slow_draft(service, dataset_id: str, loops: int = 2_000_000):
    """Create a validated draft whose next() busy-loops so runs exceed a short timeout."""
    spec = canonical_spec(dataset_id, "single_data_indicator", "single_test")
    service.validate_strategy_spec(spec)
    draft = service.create_strategy_draft(spec)
    draft_id = draft["draft_id"]
    snapshot = service.get_strategy_draft(draft_id)
    relative = "test_strategy.py"
    file_hash = snapshot["manifest"][relative]
    path = service.settings.state_root / "drafts" / draft_id / relative
    content = path.read_text(encoding="utf-8")
    content = content.replace(
        "    def next(self):\n",
        f"    def next(self):\n        for _ in range({loops}): pass\n",
        1,
    )
    service.update_strategy_draft(draft_id, relative, content, snapshot["revision"], file_hash)
    validation = service.validate_strategy_draft(draft_id, snapshot["revision"] + 1)
    return draft_id, validation


def test_cancel_during_active_run(registered_dataset):
    service, dataset = registered_dataset
    draft_id, validation = _make_slow_draft(service, dataset["dataset_id"])
    plan = service.prepare_strategy_run(
        draft_id,
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        20,
        "fixed_tests",
        "prepare-cancel-active",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"],
        plan["run_token"],
        approval["approval_id"],
        "start-cancel-active",
    )
    _wait_for_state(service, started["job_id"], "RUNNING")
    cancelled = service.cancel_strategy_run(started["job_id"], "cancel-active")
    assert cancelled["state"] in {"CANCELLED", "CANCEL_REQUESTED"}
    status = _wait(service, started["job_id"], timeout=15.0)
    assert status["state"] == "CANCELLED", status.get("error")


def test_timeout_kills_run(registered_dataset):
    service, dataset = registered_dataset
    draft_id, validation = _make_slow_draft(service, dataset["dataset_id"], loops=5_000_000)
    plan = service.prepare_strategy_run(
        draft_id,
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        2,
        "fixed_tests",
        "prepare-timeout",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"],
        plan["run_token"],
        approval["approval_id"],
        "start-timeout",
    )
    status = _wait(service, started["job_id"], timeout=20.0)
    assert status["state"] == "TIMED_OUT", status.get("error")


def test_real_crash_recovery(registered_dataset):
    service, dataset = registered_dataset
    draft_id, validation = _make_slow_draft(service, dataset["dataset_id"], loops=8_000_000)
    plan = service.prepare_strategy_run(
        draft_id,
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        30,
        "fixed_tests",
        "prepare-crash",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"],
        plan["run_token"],
        approval["approval_id"],
        "start-crash",
    )
    _wait_for_state(service, started["job_id"], "RUNNING")
    # Wait for the candidate child pid to be recorded, then kill both processes.
    deadline = time.monotonic() + 10.0
    job = service.state.get("job", started["job_id"])
    while time.monotonic() < deadline and not job.get("child_pid"):
        time.sleep(0.1)
        job = service.state.get("job", started["job_id"])
    for pid_key in ("child_pid", "worker_pid"):
        pid = job.get(pid_key)
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    # Ensure zombies are reaped so _pid_alive can detect the dead workers.
    for pid_key in ("child_pid", "worker_pid"):
        pid = job.get(pid_key)
        if pid:
            try:
                os.waitpid(pid, 0)
            except (OSError, ChildProcessError):
                pass
    status = service.get_run_status(started["job_id"])
    assert status["state"] == "ORPHANED", status.get("error")
