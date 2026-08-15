from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backtrader_mcp.errors import InvalidRequest, NotFound


def _iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _put_job(service, job_id: str, state: str = "RUNNING", **overrides) -> dict:
    job = {
        "job_id": job_id,
        "state": state,
        "run_plan_id": "runplan_x",
        "draft_id": "draft_x",
        "run_profile_id": "fixed_tests",
        "created_at": _iso(60),
        "started_at": _iso(30),
        "finished_at": None,
        "timeout_seconds": 300,
        "worker_pid": os.getpid(),
        "error": None,
    }
    job.update(overrides)
    service.state.put("job", job_id, job)
    return job


def test_list_jobs_orders_and_filters(service_env):
    service, _, _ = service_env
    _put_job(service, "job_" + "a" * 32, state="RUNNING", created_at=_iso(60))
    _put_job(service, "job_" + "b" * 32, state="SUCCEEDED", created_at=_iso(30))
    _put_job(service, "job_" + "c" * 32, state="ORPHANED", created_at=_iso(10))
    result = service.list_jobs()
    assert result["total"] == 3
    assert [job["job_id"] for job in result["jobs"]] == [
        "job_" + "c" * 32,
        "job_" + "b" * 32,
        "job_" + "a" * 32,
    ]
    running = service.list_jobs(state="RUNNING")
    assert running["total"] == 1
    assert running["jobs"][0]["state"] == "RUNNING"
    active = service.list_jobs(state="active")
    assert active["total"] == 1
    assert set(active["jobs"][0].keys()) == {
        "job_id",
        "state",
        "draft_id",
        "run_profile_id",
        "created_at",
        "started_at",
        "finished_at",
        "error",
    }
    with pytest.raises(InvalidRequest, match="valid states"):
        service.list_jobs(state="NOPE")


def test_list_jobs_pagination(service_env):
    service, _, _ = service_env
    for index in range(5):
        _put_job(service, f"job_{index:032x}", state="SUCCEEDED", created_at=_iso(100 - index))
    page1 = service.list_jobs(limit=2, offset=0)
    assert len(page1["jobs"]) == 2
    assert page1["has_more"] is True
    assert page1["total"] == 5
    page2 = service.list_jobs(limit=2, offset=4)
    assert len(page2["jobs"]) == 1
    assert page2["has_more"] is False
    with pytest.raises(InvalidRequest):
        service.list_jobs(limit=101)
    with pytest.raises(InvalidRequest):
        service.list_jobs(offset=-1)


def test_job_summary_truncates_error(service_env):
    service, _, _ = service_env
    _put_job(service, "job_" + "d" * 32, state="FAILED", error="x" * 300)
    assert len(service.list_jobs(state="FAILED")["jobs"][0]["error"]) == 200


def test_get_job_logs_tails_and_sanitizes(service_env):
    service, _, _ = service_env
    job_id = "job_" + "e" * 32
    _put_job(service, job_id, state="FAILED")
    job_root = service.settings.state_root / "jobs" / job_id
    job_root.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"line {i} of /abs/private/candidate.log" for i in range(200)) + "\n"
    (job_root / "supervisor.stderr.log").write_text(content, encoding="utf-8")
    (job_root / "supervisor.stdout.log").write_text("short stdout\n", encoding="utf-8")
    result = service.get_run_logs(job_id, tail_bytes=500)
    assert set(result["files"]) == {"supervisor.stderr.log", "supervisor.stdout.log"}
    stderr = result["files"]["supervisor.stderr.log"]
    assert stderr["truncated"] is True
    assert "/abs/private" not in stderr["content"]
    assert "<path>" in stderr["content"]
    assert result["files"]["supervisor.stdout.log"]["truncated"] is False


def test_get_job_logs_rejects_traversal_ids(service_env):
    service, _, _ = service_env
    for bad_id in ("../../etc/passwd", "job_XYZ", "job_" + "f" * 31, "job_" + "f" * 33):
        with pytest.raises(InvalidRequest, match="job_id"):
            service.get_run_logs(bad_id)


def test_get_job_logs_bounds_tail_bytes(service_env):
    service, _, _ = service_env
    job_id = "job_" + "f" * 32
    _put_job(service, job_id)
    with pytest.raises(InvalidRequest, match="tail_bytes"):
        service.get_run_logs(job_id, tail_bytes=0)
    with pytest.raises(InvalidRequest, match="tail_bytes"):
        service.get_run_logs(job_id, tail_bytes=25001)


def test_get_job_logs_missing_job_raises_not_found(service_env):
    service, _, _ = service_env
    with pytest.raises(NotFound):
        service.get_run_logs("job_" + "f" * 32)


def test_get_run_status_derives_polling_fields(service_env):
    service, _, _ = service_env
    job_id = "job_" + "9" * 32
    _put_job(service, job_id, state="QUEUED")
    status = service.get_run_status(job_id)
    assert status["log_uri"] == f"backtrader-mcp://jobs/{job_id}/logs"
    assert status["elapsed_seconds"] >= 59.0
    assert status["eta_bound"] is not None
    eta = datetime.fromisoformat(status["eta_bound"])
    started = datetime.fromisoformat(status["started_at"])
    assert eta == started + timedelta(seconds=300)
    done_id = "job_" + "8" * 32
    _put_job(service, done_id, state="SUCCEEDED", finished_at=_iso(10))
    done = service.get_run_status(done_id)
    assert done["eta_bound"] is None
    assert done["elapsed_seconds"] >= 49.0
    assert done["log_uri"] == f"backtrader-mcp://jobs/{done_id}/logs"
