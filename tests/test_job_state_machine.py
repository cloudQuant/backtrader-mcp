from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backtrader_mcp import worker as worker_module
from backtrader_mcp.errors import Conflict, InvalidRequest, NotFound
from backtrader_mcp.settings import Settings


def _iso(seconds_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _put_job(service, job_id: str, state: str = "RUNNING", **overrides) -> dict:
    job = {
        "job_id": job_id,
        "state": state,
        "run_plan_id": "runplan_x",
        "draft_id": "draft_x",
        "run_profile_id": "fixed_tests",
        "created_at": _iso(3600),
        "started_at": _iso(600),
        "finished_at": None,
        "timeout_seconds": 300,
        "worker_pid": os.getpid(),
        "child_pid": None,
        "heartbeat_at": _iso(1),
        "error": None,
    }
    job.update(overrides)
    service.state.put("job", job_id, job)
    return job


# ---------------------------------------------------------------------------
# 任务 1：StateStore CAS 原语
# ---------------------------------------------------------------------------


def test_update_precondition_failure_raises_conflict_and_preserves_object(service_env):
    service, _, _ = service_env
    job_id = "job_" + "1" * 32
    _put_job(service, job_id, state="RUNNING")
    with pytest.raises(Conflict, match="precondition failed"):
        service.state.update(
            "job",
            job_id,
            lambda current: {**current, "state": "SUCCEEDED"},
            expected=lambda current: current["state"] == "QUEUED",
        )
    assert service.state.get("job", job_id)["state"] == "RUNNING"


def test_update_precondition_success_applies_mutation(service_env):
    service, _, _ = service_env
    job_id = "job_" + "2" * 32
    _put_job(service, job_id, state="RUNNING")
    updated = service.state.update(
        "job",
        job_id,
        lambda current: {**current, "state": "SUCCEEDED", "finished_at": _iso(0)},
        expected=lambda current: current["state"] in {"RUNNING", "QUEUED"},
    )
    assert updated["state"] == "SUCCEEDED"
    assert service.state.get("job", job_id)["state"] == "SUCCEEDED"


def test_state_store_delete_and_checkpoint(service_env):
    service, _, _ = service_env
    job_id = "job_" + "3" * 32
    _put_job(service, job_id, state="SUCCEEDED", finished_at=_iso(10))
    service.state.delete("job", job_id)
    with pytest.raises(NotFound):
        service.state.get("job", job_id)
    service.state.checkpoint()


# ---------------------------------------------------------------------------
# 任务 2：worker 终态 CAS 与 error_kind 分类
# ---------------------------------------------------------------------------


def test_classify_exit_signal_death_is_resource_limit():
    kind, detail = worker_module._classify_exit(-9)
    assert kind == "resource_limit"
    assert "SIGKILL" in detail


def test_classify_exit_positive_is_user_strategy():
    kind, detail = worker_module._classify_exit(1)
    assert kind == "user_strategy"
    assert "exited 1" in detail


def test_classify_exit_zero_is_none():
    assert worker_module._classify_exit(0) is None


def test_write_terminal_suppresses_on_terminal_state(service_env):
    service, _, _ = service_env
    job_id = "job_" + "4" * 32
    _put_job(service, job_id, state="SUCCEEDED", finished_at=_iso(10))
    result = worker_module._write_terminal(
        service.state, job_id, "FAILED", "late failure", "user_strategy"
    )
    assert result is None
    assert service.state.get("job", job_id)["state"] == "SUCCEEDED"


def test_write_terminal_suppresses_on_cancel_requested(service_env):
    service, _, _ = service_env
    job_id = "job_" + "5" * 32
    _put_job(service, job_id, state="CANCEL_REQUESTED")
    result = worker_module._write_terminal(
        service.state, job_id, "SUCCEEDED", "finished anyway", None
    )
    assert result is None
    assert service.state.get("job", job_id)["state"] == "CANCEL_REQUESTED"


def test_write_terminal_persists_on_active_state(service_env):
    service, _, _ = service_env
    job_id = "job_" + "6" * 32
    _put_job(service, job_id, state="RUNNING")
    result = worker_module._write_terminal(
        service.state, job_id, "FAILED", "strategy crashed", "user_strategy"
    )
    assert result is not None
    final = service.state.get("job", job_id)
    assert final["state"] == "FAILED"
    assert final["error_kind"] == "user_strategy"


def test_write_running_requires_queued(service_env):
    service, _, _ = service_env
    job_id = "job_" + "7" * 32
    _put_job(service, job_id, state="CANCELLED", finished_at=_iso(1))
    result = worker_module._write_running(service.state, job_id)
    assert result is None
    assert service.state.get("job", job_id)["state"] == "CANCELLED"


# ---------------------------------------------------------------------------
# 任务 3：cancel / get_run_status / 恢复 CAS 仲裁
# ---------------------------------------------------------------------------


def test_cancel_on_terminal_job_returns_already_terminal_without_killing(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "8" * 32
    _put_job(service, job_id, state="SUCCEEDED", finished_at=_iso(10))
    calls: list[int] = []
    monkeypatch.setattr("backtrader_mcp.jobs.terminate_pid", lambda pid: calls.append(pid))
    response = service.cancel_strategy_run(job_id, "idem-key-terminal")
    assert response["already_terminal"] is True
    assert response["state"] == "SUCCEEDED"
    assert calls == []
    assert service.state.get("job", job_id)["state"] == "SUCCEEDED"


def test_get_run_status_does_not_overwrite_succeeded_job(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "9" * 32
    _put_job(service, job_id, state="SUCCEEDED", finished_at=_iso(10), worker_pid=99999999)
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: False)
    status = service.get_run_status(job_id)
    assert status["state"] == "SUCCEEDED"


def test_get_run_status_orphans_running_job_with_dead_worker(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "a" * 32
    _put_job(service, job_id, state="RUNNING", worker_pid=99999998)
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: False)
    status = service.get_run_status(job_id)
    assert status["state"] == "ORPHANED"
    assert status["error_kind"] == "orphaned"


def test_recover_jobs_uses_cas(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "b" * 32
    _put_job(service, job_id, state="RUNNING", worker_pid=99999997)
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: False)
    recovered = service.jobs.recover_jobs()
    assert job_id in recovered
    assert service.state.get("job", job_id)["state"] == "ORPHANED"


# ---------------------------------------------------------------------------
# 任务 4：watchdog
# ---------------------------------------------------------------------------


def _terminal_pid_calls(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr("backtrader_mcp.jobs.terminate_pid", lambda pid: calls.append(pid))
    return calls


def test_watchdog_orphans_dead_worker_and_cleans_candidate(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "c" * 32
    _put_job(
        service,
        job_id,
        state="RUNNING",
        worker_pid=99999996,
        child_pid=99999995,
    )
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: False)
    calls = _terminal_pid_calls(monkeypatch)
    report = service.jobs.watchdog_tick()
    assert report["enforced"] == [{"job_id": job_id, "decision": "orphan"}]
    final = service.state.get("job", job_id)
    assert final["state"] == "ORPHANED"
    assert final["error_kind"] == "orphaned"
    assert calls == [99999995]


def test_watchdog_times_out_stalled_heartbeat(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "d" * 32
    _put_job(
        service,
        job_id,
        state="RUNNING",
        worker_pid=99999994,
        child_pid=99999993,
        heartbeat_at=_iso(60),
    )
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: True)
    calls = _terminal_pid_calls(monkeypatch)
    report = service.jobs.watchdog_tick()
    assert report["enforced"] == [{"job_id": job_id, "decision": "timeout"}]
    final = service.state.get("job", job_id)
    assert final["state"] == "TIMED_OUT"
    assert final["error_kind"] == "timeout"
    assert set(calls) == {99999994, 99999993}


def test_watchdog_enforces_wall_clock_deadline(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "e" * 32
    _put_job(
        service,
        job_id,
        state="RUNNING",
        started_at=_iso(600),
        timeout_seconds=60,
        heartbeat_at=_iso(1),
    )
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: True)
    report = service.jobs.watchdog_tick()
    assert report["enforced"] == [{"job_id": job_id, "decision": "timeout"}]
    assert service.state.get("job", job_id)["state"] == "TIMED_OUT"


def test_watchdog_ignores_terminal_jobs(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "f" * 32
    _put_job(service, job_id, state="SUCCEEDED", finished_at=_iso(10))
    calls = _terminal_pid_calls(monkeypatch)
    report = service.jobs.watchdog_tick()
    assert report["enforced"] == []
    assert calls == []
    assert service.state.get("job", job_id)["state"] == "SUCCEEDED"


def test_watchdog_thread_lifecycle(service_env):
    service, _, _ = service_env
    watchdog = service.jobs.start_watchdog()
    assert watchdog.is_running()
    watchdog.stop()
    assert not watchdog.is_running()


# ---------------------------------------------------------------------------
# 任务 5：原子并发闸门与幂等复查
# ---------------------------------------------------------------------------


def test_concurrency_capacity_check_rejects_with_suggestion(service_env):
    from dataclasses import replace

    service, _, _ = service_env
    _put_job(service, "job_" + "a1" * 16, state="RUNNING")
    service.jobs.settings = replace(service.jobs.settings, max_concurrent_jobs=1)
    with pytest.raises(Conflict) as caught:
        service.jobs._assert_capacity()
    assert "list_jobs" in caught.value.suggestion
    assert len(service.state.list("job")) == 1


def test_timeout_seconds_rejects_bool(service_env):
    service, _, _ = service_env
    with pytest.raises(InvalidRequest, match="timeout_seconds"):
        service.prepare_strategy_run("draft_missing", "token", "ds_missing", "default", True)


# ---------------------------------------------------------------------------
# 任务 6：保留策略
# ---------------------------------------------------------------------------


def test_clean_jobs_removes_only_expired_terminal_jobs(service_env, tmp_path):
    service, _, _ = service_env
    expired = "job_" + "b1" * 16
    recent = "job_" + "b2" * 16
    active = "job_" + "b3" * 16
    _put_job(service, expired, state="SUCCEEDED", finished_at=_iso(86400 * 2))
    _put_job(service, recent, state="FAILED", finished_at=_iso(60))
    _put_job(service, active, state="RUNNING", finished_at=None)
    job_root = service.settings.state_root / "jobs" / expired
    job_root.mkdir(parents=True, exist_ok=True)
    (job_root / "supervisor.stderr.log").write_text("x\n", encoding="utf-8")
    result = service.jobs.clean_jobs(_iso(86400))
    assert result["deleted_rows"] == 1
    assert result["removed_dirs"] == 1
    remaining = {job["job_id"] for job in service.state.list("job")}
    assert remaining == {recent, active}
    assert not (service.settings.state_root / "jobs" / expired).exists()
    audits = [row["event"] for row in service.state.list_audit(10)]
    assert "clean.jobs" in audits


def test_doctor_reports_job_statistics_when_state_exists(service_env):
    from backtrader_mcp.doctor import doctor_report

    service, _, _ = service_env
    _put_job(service, "job_" + "c1" * 16, state="RUNNING", created_at=_iso(700))
    _put_job(service, "job_" + "c2" * 16, state="SUCCEEDED", finished_at=_iso(10))
    _put_job(service, "job_" + "c3" * 16, state="ORPHANED", finished_at=_iso(20))
    report = doctor_report(service.settings)
    jobs = report["jobs"]
    assert jobs["initialized"] is True
    assert jobs["counts"]["RUNNING"] == 1
    assert jobs["counts"]["SUCCEEDED"] == 1
    assert jobs["counts"]["ORPHANED"] == 1
    assert jobs["oldest_active_job"]["job_id"] == "job_" + "c1" * 16
    assert isinstance(jobs["wal_bytes"], int)


def test_doctor_jobs_section_is_absent_without_state(tmp_path):
    from backtrader_mcp.doctor import doctor_report

    state = tmp_path / "never-created-state"
    settings = Settings(state_root=state, source_roots={}, target_roots={}, runtimes={})
    report = doctor_report(settings)
    assert report["jobs"] is None
    assert not state.exists(), "doctor must not initialize the state root"


def test_cli_clean_jobs_kind_removes_expired_terminal_jobs(service_env):
    from backtrader_mcp.cli import _clean_records

    service, _, _ = service_env
    expired = "job_" + "d1" * 16
    _put_job(service, expired, state="SUCCEEDED", finished_at=_iso(86400 * 2))
    job_root = service.settings.state_root / "jobs" / expired
    job_root.mkdir(parents=True, exist_ok=True)
    (job_root / "supervisor.stderr.log").write_text("x\n", encoding="utf-8")
    result = _clean_records(service, "jobs", _iso(86400))
    assert result["kind"] == "jobs"
    assert result["deleted_rows"] == 1
    assert result["removed_dirs"] == 1
    assert service.state.list("job") == []


# ---------------------------------------------------------------------------
# 审查补测：CAS 冲突重读、cancel 两段 CAS、worker 助手、clean 输入校验
# ---------------------------------------------------------------------------


def test_get_run_status_conflict_reports_latest_state(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "e1" * 16
    _put_job(service, job_id, state="RUNNING", worker_pid=99999990)
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: False)
    original_update = service.state.update

    def racing_update(kind, object_id, mutator, *, expected=None):
        if kind == "job" and object_id == job_id and expected is not None:
            # Watchdog wins the CAS first, then our orphan write conflicts.
            original_update(
                kind,
                object_id,
                lambda current: {
                    **current,
                    "state": "TIMED_OUT",
                    "finished_at": _iso(0),
                    "error": "watchdog deadline",
                    "error_kind": "timeout",
                },
                expected=lambda current: current.get("state") in {"RUNNING", "QUEUED"},
            )
            raise Conflict(f"job precondition failed: {object_id}")
        return original_update(kind, object_id, mutator, expected=expected)

    monkeypatch.setattr(service.state, "update", racing_update)
    status = service.get_run_status(job_id)
    assert status["state"] == "TIMED_OUT"
    assert status["error_kind"] == "timeout"


def test_cancel_active_job_two_stage_cas(service_env, monkeypatch):
    service, _, _ = service_env
    job_id = "job_" + "e2" * 16
    _put_job(service, job_id, state="RUNNING", worker_pid=12345, child_pid=12346)
    monkeypatch.setattr("backtrader_mcp.jobs._pid_alive", lambda pid: True)
    kills: list[int] = []
    monkeypatch.setattr("backtrader_mcp.jobs.terminate_pid", lambda pid: kills.append(pid))
    response = service.cancel_strategy_run(job_id, "idem-two-stage")
    assert response["state"] == "CANCELLED"
    assert response["already_terminal"] is False
    assert set(kills) == {12345, 12346}
    final = service.state.get("job", job_id)
    assert final["state"] == "CANCELLED"
    assert final["error_kind"] == "cancelled"


def test_write_cancelled_requires_cancel_requested(service_env):
    service, _, _ = service_env
    job_id = "job_" + "e3" * 16
    _put_job(service, job_id, state="RUNNING")
    result = worker_module._write_cancelled(service.state, job_id, "cancelled late")
    assert result is None
    assert service.state.get("job", job_id)["state"] == "RUNNING"


def test_heartbeat_ignores_terminal_jobs(service_env):
    service, _, _ = service_env
    job_id = "job_" + "e4" * 16
    heartbeat_before = _iso(5)
    _put_job(
        service, job_id, state="SUCCEEDED", finished_at=_iso(10), heartbeat_at=heartbeat_before
    )
    worker_module._heartbeat(service.state, job_id)
    final = service.state.get("job", job_id)
    assert final["state"] == "SUCCEEDED"
    assert final["heartbeat_at"] == heartbeat_before


def test_clean_jobs_rejects_invalid_before(service_env):
    service, _, _ = service_env
    with pytest.raises(InvalidRequest, match="ISO date"):
        service.jobs.clean_jobs("abc")
