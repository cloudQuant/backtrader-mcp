from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from backtrader_mcp import backtrader_runtime, cli
from backtrader_mcp.service import BacktraderMCPService
from backtrader_mcp.settings import Settings
from backtrader_mcp.util import utc_now


@pytest.fixture()
def cli_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> BacktraderMCPService:
    monkeypatch.setenv("BACKTRADER_MCP_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("BACKTRADER_MCP_SOURCE_ROOTS", "{}")
    monkeypatch.setenv("BACKTRADER_MCP_TARGET_ROOTS", "{}")
    monkeypatch.setenv("BACKTRADER_MCP_RUNTIMES", "{}")
    return BacktraderMCPService(Settings.from_env())


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def _terminal_job(job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "state": "SUCCEEDED",
        "draft_id": "draft_example",
        "run_profile_id": "fixed_tests",
        "created_at": utc_now(),
        "started_at": utc_now(),
        "finished_at": utc_now(),
        "error": "x" * 250,
    }


def test_cli_lists_and_shows_terminal_jobs(cli_service: BacktraderMCPService, capsys):
    job_id = "job_" + "1" * 32
    cli_service.state.put("job", job_id, _terminal_job(job_id))

    assert cli.main(["list", "--kind", "job", "--state", "SUCCEEDED", "--limit", "1"]) == 0
    listed = _json_stdout(capsys)
    assert listed["kind"] == "job"
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["job_id"] == job_id
    assert item["error"] == "x" * 200

    assert cli.main(["show", "--kind", "job", "--id", job_id]) == 0
    shown = _json_stdout(capsys)
    assert shown["job_id"] == job_id
    assert shown["state"] == "SUCCEEDED"


def test_cli_exposes_logs_and_machine_readable_not_found(
    cli_service: BacktraderMCPService, capsys, tmp_path: Path
):
    job_id = "job_" + "2" * 32
    cli_service.state.put("job", job_id, _terminal_job(job_id))
    log_path = tmp_path / "state" / "jobs" / job_id / "supervisor.stdout.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("controlled output\n", encoding="utf-8")

    assert cli.main(["logs", "--job", job_id]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "===== supervisor.stdout.log =====" in captured.err
    assert "controlled output" in captured.err

    assert cli.main(["logs", "--job", "job_missing"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "not_found"


def test_cli_cleans_records_and_runs_audit_and_recovery(cli_service: BacktraderMCPService, capsys):
    cli_service.state.audit("test.audit", "subject", {"value": 1})
    cli_service.state.idempotent_put("test", "key", {"request": 1}, {"response": 1})

    assert cli.main(["clean", "--kind", "audit", "--before", "9999-01-01"]) == 0
    cleaned_audit = _json_stdout(capsys)
    assert cleaned_audit["kind"] == "audit"
    assert cleaned_audit["deleted"] >= 1

    assert cli.main(["clean", "--kind", "idempotency", "--before", "9999-01-01"]) == 0
    cleaned_idempotency = _json_stdout(capsys)
    assert cleaned_idempotency["kind"] == "idempotency"
    assert cleaned_idempotency["deleted"] == 1

    assert cli.main(["audit-independence"]) == 0
    audit = _json_stdout(capsys)
    assert audit["status"] == "passed"
    assert audit["findings"] == []

    assert cli.main(["recover"]) == 0
    recovery = _json_stdout(capsys)
    assert recovery == {"jobs": [], "transactions": []}


def test_cli_exposes_the_cloudquant_backtrader_installer(monkeypatch, capsys):
    expected = {
        "status": "warning",
        "action": "warning_existing_untrusted",
        "warning": {"code": "installed_backtrader_untrusted"},
    }
    monkeypatch.setattr(backtrader_runtime, "ensure_cloudquant_backtrader", lambda: expected)

    assert cli.main(["install-backtrader"]) == 0
    assert _json_stdout(capsys) == expected


def test_cli_approve_requires_confirmation_and_preserves_error_contract(
    cli_service: BacktraderMCPService, capsys, monkeypatch: pytest.MonkeyPatch
):
    with pytest.raises(SystemExit) as non_tty:
        cli.main(["approve", "--change-set", "change_missing", "--change-token", "bad"])
    assert non_tty.value.code == 2
    assert "--yes is required when stdin is not a TTY" in capsys.readouterr().err

    class TtyInput:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr(cli.sys, "stdin", TtyInput())
    monkeypatch.setattr(builtins, "input", lambda _: "wrong-subject")
    assert cli.main(["approve", "--change-set", "change_missing", "--change-token", "bad"]) == 2
    assert capsys.readouterr().err == "approval cancelled\n"

    assert (
        cli.main(["approve", "--change-set", "change_missing", "--change-token", "bad", "--yes"])
        == 2
    )
    error = capsys.readouterr()
    assert error.out == ""
    assert json.loads(error.err)["code"] == "forbidden"


def test_cli_show_missing_object_returns_product_error_json(
    cli_service: BacktraderMCPService, capsys
):
    assert cli.main(["show", "--kind", "draft", "--id", "draft_missing"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "code": "not_found",
        "message": "draft not found: draft_missing",
    }
