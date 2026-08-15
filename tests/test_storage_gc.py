from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backtrader_mcp.errors import InvalidRequest

COLUMN_MAP = {
    "datetime": "datetime",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def _iso(seconds_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _touch(path, seconds_ago: float) -> None:
    stamp = (datetime.now() - timedelta(seconds=seconds_ago)).timestamp()
    os.utime(path, (stamp, stamp))


def test_clean_cas_preserves_referenced_objects(service_env):
    service, source, _ = service_env
    manifest = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    cas_root = service.settings.state_root / "cas"
    referenced = service.settings.state_root / manifest["extensions"]["cas_relative_path"]
    unreferenced = cas_root / "sha256" / "ab" / ("ab" + "c" * 62 + ".csv")
    unreferenced.parent.mkdir(parents=True, exist_ok=True)
    unreferenced.write_bytes(b"orphan")
    _touch(unreferenced, 86400 * 2)
    foreign = cas_root / "sha256" / "ab" / "notes.txt"
    foreign.write_text("keep me", encoding="utf-8")
    _touch(foreign, 86400 * 2)
    result = service.datasets.clean_cas(_iso(86400))
    assert result["removed_objects"] == 1
    assert referenced.exists()
    assert foreign.exists()
    assert not unreferenced.exists()


def test_clean_cas_rejects_invalid_before(service_env):
    service, _, _ = service_env
    with pytest.raises(InvalidRequest, match="ISO date"):
        service.datasets.clean_cas("abc")


def test_clean_drafts_skips_referenced_drafts(service_env):
    service, _, _ = service_env
    referenced = service.create_strategy_draft(
        {
            "spec_version": "strategy-spec-v1",
            "name": "kept",
            "slug": "kept",
            "category": "strategy",
            "archetype": "single_data_indicator",
            "output_profile": "single_test",
            "dataset_id": "ds_" + "d" * 64,
            "feeds": [{"name": "primary", "dataset_feed": "primary"}],
            "parameters": {"period": 5},
            "entry": {"rule": "template"},
            "exit": {"rule": "template"},
            "sizing": {"mode": "fixed_fraction", "starting_cash": 100000.0},
            "risk": {"commission": 0.001, "live_trading": False},
            "run_modes": ["runonce"],
            "allowed_imports": ["backtrader"],
        }
    )
    service.state.put(
        "run_plan",
        "runplan_keep",
        {"run_plan_id": "runplan_keep", "draft_id": referenced["draft_id"], "status": "prepared"},
    )
    old = service.create_strategy_draft(
        {
            "spec_version": "strategy-spec-v1",
            "name": "old",
            "slug": "old",
            "category": "strategy",
            "archetype": "single_data_indicator",
            "output_profile": "single_test",
            "dataset_id": "ds_" + "d" * 64,
            "feeds": [{"name": "primary", "dataset_feed": "primary"}],
            "parameters": {"period": 5},
            "entry": {"rule": "template"},
            "exit": {"rule": "template"},
            "sizing": {"mode": "fixed_fraction", "starting_cash": 100000.0},
            "risk": {"commission": 0.001, "live_trading": False},
            "run_modes": ["runonce"],
            "allowed_imports": ["backtrader"],
        }
    )
    service.state.update(
        "draft",
        old["draft_id"],
        lambda current: {**current, "created_at": _iso(86400 * 2)},
    )
    result = service.drafts.clean_drafts(_iso(86400))
    assert result["deleted_rows"] == 1
    assert service.state.maybe_get("draft", old["draft_id"]) is None
    assert service.state.maybe_get("draft", referenced["draft_id"]) is not None
    assert (service.settings.state_root / "drafts" / old["draft_id"]).exists() is False


def test_clean_approvals_deletes_used_and_expired(service_env):
    service, _, _ = service_env
    used = service.state.create_approval("run", "subject", "hash", _iso(-86400))
    service.state.consume_approval(used["approval_id"], "run", "subject", "hash")
    service.state.connect().execute(
        "UPDATE approvals SET used_at=? WHERE approval_id=?",
        (_iso(86400 * 2), used["approval_id"]),
    )
    service.state.create_approval("run", "subject2", "hash2", _iso(86400 * 2))
    future = service.state.create_approval("run", "subject3", "hash3", _iso(-86400))
    deleted = service.state.clean_approvals(_iso(0))
    assert deleted == 2
    remaining = [row["approval_id"] for row in service.state.list_approvals()]
    assert remaining == [future["approval_id"]]


def test_cli_clean_cas_kind(service_env):
    from backtrader_mcp.cli import _clean_records

    service, source, _ = service_env
    service.register_dataset("market", "prices.csv", COLUMN_MAP)
    cas_root = service.settings.state_root / "cas"
    orphan = cas_root / "sha256" / "cd" / ("cd" + "d" * 62 + ".csv")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    _touch(orphan, 86400 * 2)
    result = _clean_records(service, "cas", _iso(86400))
    assert result["kind"] == "cas"
    assert result["removed_objects"] == 1
