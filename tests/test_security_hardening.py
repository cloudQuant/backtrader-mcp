from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import backtrader_mcp.reports as reports_module
from backtrader_mcp.errors import Forbidden
from backtrader_mcp.security import TokenSigner
from backtrader_mcp.state import StateStore


def _signer(tmp_path: Path, with_state: bool = True) -> TokenSigner:
    root = tmp_path / "state"
    root.mkdir()
    state = StateStore(root) if with_state else None
    return TokenSigner(root, state=state)


def test_nonce_replay_is_rejected(tmp_path):
    signer = _signer(tmp_path)
    token = signer.issue("change", {"change_id": "c1"})
    assert signer.verify(token, "change") == {"change_id": "c1"}
    with pytest.raises(Forbidden, match="already used"):
        signer.verify(token, "change")


def test_approve_then_landing_point_consumes_nonce_once(tmp_path):
    signer = _signer(tmp_path)
    token = signer.issue("run_plan", {"run_plan_id": "p1"})
    # approve path does not consume
    assert signer.verify(token, "run_plan", consume_nonce=False) == {"run_plan_id": "p1"}
    # landing point consumes
    assert signer.verify(token, "run_plan") == {"run_plan_id": "p1"}
    with pytest.raises(Forbidden, match="already used"):
        signer.verify(token, "run_plan")


def test_token_without_state_skips_nonce_ledger(tmp_path):
    signer = _signer(tmp_path, with_state=False)
    token = signer.issue("change", {"change_id": "c1"})
    assert signer.verify(token, "change") == {"change_id": "c1"}
    assert signer.verify(token, "change") == {"change_id": "c1"}


def test_expired_token_at_exact_expiry_is_rejected(tmp_path):
    import time

    signer = _signer(tmp_path)
    now = int(time.time())
    payload = {
        "v": 1,
        "kind": "change",
        "iat": now - 10,
        "exp": now,  # exp == now must be rejected (<= comparison)
        "nonce": "a" * 32,
        "claims": {"change_id": "c1"},
    }
    import hashlib
    import hmac

    from backtrader_mcp.security import b64url_encode, canonical_json

    encoded = b64url_encode(canonical_json(payload).encode("utf-8"))
    signature = b64url_encode(hmac.new(signer._secret, encoded.encode(), hashlib.sha256).digest())
    with pytest.raises(Forbidden, match="expired"):
        signer.verify(f"{encoded}.{signature}", "change")


def test_iat_future_skew_is_rejected_and_past_is_exp_governed(tmp_path):
    import hashlib
    import hmac
    import time

    from backtrader_mcp.security import b64url_encode, canonical_json

    signer = _signer(tmp_path)
    now = int(time.time())
    # Future issuance beyond the skew window is rejected.
    payload = {
        "v": 1,
        "kind": "change",
        "iat": now + 400,
        "exp": now + 900,
        "nonce": "b" * 32,
        "claims": {"change_id": "c1"},
    }
    encoded = b64url_encode(canonical_json(payload).encode("utf-8"))
    signature = b64url_encode(hmac.new(signer._secret, encoded.encode(), hashlib.sha256).digest())
    with pytest.raises(Forbidden, match="timestamp"):
        signer.verify(f"{encoded}.{signature}", "change")
    # Past issuance within exp is accepted (human approval latency).
    signer._state.issue_nonce("b" * 32)
    payload["iat"] = now - 400
    encoded = b64url_encode(canonical_json(payload).encode("utf-8"))
    signature = b64url_encode(hmac.new(signer._secret, encoded.encode(), hashlib.sha256).digest())
    assert signer.verify(f"{encoded}.{signature}", "change") == {"change_id": "c1"}


def test_array_payload_is_rejected(tmp_path):
    signer = _signer(tmp_path)
    import hashlib
    import hmac

    from backtrader_mcp.security import b64url_encode

    encoded = b64url_encode(json.dumps([1, 2, 3]).encode("utf-8"))
    signature = b64url_encode(hmac.new(signer._secret, encoded.encode(), hashlib.sha256).digest())
    with pytest.raises(Forbidden, match="malformed"):
        signer.verify(f"{encoded}.{signature}", "change")


def test_approver_identity_is_recorded_in_audit(service_env):
    service, _, _ = service_env
    identity = service.state.create_approval("run", "subject", "hash", "2030-01-01T00:00:00+00:00")
    from backtrader_mcp.util import approver_identity

    service.state.audit(
        "approval.created_by_human",
        "subject",
        {"approval_id": identity["approval_id"], "approver": approver_identity()},
    )
    records = service.state.list_audit(5)
    record = next(row for row in records if row["event"] == "approval.created_by_human")
    assert "username" in record["details"]["approver"]
    if os.name == "posix":
        assert isinstance(record["details"]["approver"]["uid"], int)


def test_markdown_rendering_escapes_extra_metric_names():
    result = {
        "schema_version": "run-result-v1",
        "run_id": "job_x",
        "status": "passed",
        "result_hash": "h",
        "metrics": {
            "bar_num": 1,
            "buy_count": 0,
            "sell_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "trade_num": 0,
            "final_value": 1.0,
            "sharpe_ratio": None,
            "annual_return": None,
            "max_drawdown": 0.0,
            "return_rate": 0.0,
            "evil[link](https://x)": 1.0,
        },
        "diagnostics": [],
    }
    rendered = reports_module.render_markdown(result)
    assert "evil[link](https://x)" not in rendered
    assert "evil_link__https___x_" in rendered


def test_worker_identifier_contract(service_env):
    import backtrader_mcp.worker as worker_module

    service, _, _ = service_env
    service.register_dataset(
        "market",
        "prices.csv",
        {
            "datetime": "datetime",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        },
    )
    feed_configs = [
        {
            "name": "primary",
            "input_format": "generic_csv",
            "adapter": "backtrader.feeds.GenericCSVData",
            "bar_operation": {"mode": "direct"},
        }
    ]
    base = {
        "schema_version": "run-result-v1",
        "run_mode": "runonce",
        "metrics": {
            "bar_num": 10,
            "buy_count": 0,
            "sell_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "trade_num": 0,
            "final_value": 1.0,
            "sharpe_ratio": None,
            "annual_return": None,
            "max_drawdown": 0.0,
            "return_rate": 0.0,
        },
        "feed_runtime": [
            {
                "dataset_feed": "primary",
                "strategy_feed": "primary",
                "input_format": "generic_csv",
                "adapter": "backtrader.feeds.GenericCSVData",
                "bar_operation": {"mode": "direct"},
                "constructed_class": "GenericCSVData",
                "registered_class": "GenericCSVData",
                "source_row_count": 10,
                "output_bar_count": 10,
            }
        ],
    }
    assert worker_module._validate_result(base, feed_configs)["run_mode"] == "runonce"
    bad = json.loads(json.dumps(base))
    bad["feed_runtime"][0]["constructed_class"] = "bad name!"
    with pytest.raises(ValueError, match="invalid adapter classes"):
        worker_module._validate_result(bad, feed_configs)
    empty_registered = json.loads(json.dumps(base))
    empty_registered["feed_runtime"][0]["registered_class"] = ""
    with pytest.raises(ValueError, match="invalid adapter classes"):
        worker_module._validate_result(empty_registered, feed_configs)


def test_locks_platform_fallback(tmp_path, monkeypatch):
    import backtrader_mcp.locks as locks_module

    # POSIX path still acquires without error
    manager = locks_module.LockManager(tmp_path / "locks")
    with manager.acquire("test-lock"):
        pass
    # Simulate the Windows fallback branch
    import types

    fake_msvcrt = types.SimpleNamespace(locking=lambda *args: None, LK_LOCK=1, LK_UNLCK=0)
    monkeypatch.setattr(locks_module, "fcntl", None)
    monkeypatch.setattr(locks_module, "msvcrt", fake_msvcrt)
    manager = locks_module.LockManager(tmp_path / "locks2")
    with manager.acquire("test-lock"):
        pass


def test_resource_limit_status_probe():
    import backtrader_mcp.worker as worker_module

    status = worker_module._resource_limit_status(
        {"cpu_seconds": 30, "memory_bytes": 1000, "file_size_bytes": 10, "processes": 4}
    )
    assert {item["resource"] for item in status} == {
        "cpu_seconds",
        "memory_bytes",
        "file_size_bytes",
        "processes",
    }
    assert all("supported" in item and "requested" in item for item in status)
