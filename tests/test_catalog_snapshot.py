from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backtrader_mcp.catalog import ARCHETYPES
from backtrader_mcp.errors import InvalidRequest
from backtrader_mcp.service import BacktraderMCPService
from backtrader_mcp.settings import Settings

EXPECTED_COUNTS = {
    "functional_tests": 1152,
    "strategy_packages": 1035,
    "mapped": 1032,
}
EXPECTED_ASSET_SHA256 = "30973a10bd434e7935aa5b45577a5d5de0221a58b53a4c00a8124006438c5828"


def test_packaged_catalog_has_full_verified_metadata_and_fourteen_templates(service_env):
    service, _, _ = service_env
    snapshot = service.get_catalog_snapshot()
    assert snapshot["extensions"]["counts"] == EXPECTED_COUNTS
    assert snapshot["extensions"]["entry_count"] == 1155
    assert "entries" not in snapshot
    full_page = service.get_catalog_snapshot(include_entries=True, limit=100)
    assert full_page["pagination"]["total"] == 1155
    assert len(full_page["entries"]) == 100
    assert full_page["pagination"]["has_more"] is True
    assert full_page["pagination"]["truncated"] is True
    assert service.list_strategy_templates()["count"] == 14

    results = service.search_strategy_catalog(
        "moving average trend",
        archetype="single_data_indicator",
        limit=3,
    )
    assert len(results["entries"]) == 3
    assert all(entry["source_available"] is False for entry in results["entries"])
    inspected = service.inspect_strategy(results["entries"][0]["canonical_id"])
    assert inspected["source_attached"] is False
    assert inspected["strategy"]["entry_hash"]

    asset = (
        Path(__file__).resolve().parents[1] / "src" / "backtrader_mcp" / "catalog_snapshot.jsonl"
    )
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == EXPECTED_ASSET_SHA256


def test_source_attached_dual_corpus_refresh_is_read_only_and_detects_staleness(
    tmp_path: Path,
):
    functional = tmp_path / "functional"
    packages = tmp_path / "packages"
    target = tmp_path / "target"
    state = tmp_path / "state"
    test_dir = functional / "trend"
    package_dir = packages / "trend" / "0001_example"
    test_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    target.mkdir()
    test_path = test_dir / "test_0001_example.py"
    strategy_path = package_dir / "strategy_example.py"
    test_path.write_text(
        "import backtrader as bt\nclass Example(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    strategy_path.write_text(
        "import backtrader as bt\nclass Example(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    (package_dir / "config.yaml").write_text("period: 5\n", encoding="utf-8")
    (package_dir / "run.py").write_text("from strategy_example import Example\n", encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (test_path, strategy_path, package_dir / "config.yaml", package_dir / "run.py")
    }

    service = BacktraderMCPService(
        Settings(
            state_root=state,
            source_roots={"functional": functional, "packages": packages},
            target_roots={"strategies": target},
            runtimes={},
        )
    )
    snapshot = service.refresh_strategy_catalog(
        "functional",
        package_root_id="packages",
    )
    assert snapshot["mode"] == "source-attached"
    assert snapshot["counts"] == {
        "functional_tests": 1,
        "strategy_packages": 1,
        "mapped": 1,
    }
    assert snapshot["extensions"]["diagnostics"][0]["code"] == "verified_baseline_count_mismatch"
    entry = snapshot["entries"][0]
    assert entry["source"] == "mapped"
    assert service.inspect_strategy(entry["id"], entry["content_hash"])["status"] == "ready"
    repeated = service.refresh_strategy_catalog(
        "functional",
        expected_previous_snapshot_hash=snapshot["snapshot_hash"],
        package_root_id="packages",
    )
    assert repeated["snapshot_hash"] == snapshot["snapshot_hash"]
    after = {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (test_path, strategy_path, package_dir / "config.yaml", package_dir / "run.py")
    }
    assert after == before

    strategy_path.write_text(strategy_path.read_text(encoding="utf-8") + "# changed\n")
    assert service.inspect_strategy(entry["id"])["status"] == "stale"


def test_snapshot_default_response_is_small(service_env):
    service, _, _ = service_env
    payload = json.dumps(service.get_catalog_snapshot(), sort_keys=True)
    assert len(payload.encode("utf-8")) < 1024


def test_snapshot_pagination_pages_through_all_entries(service_env):
    service, _, _ = service_env
    seen = []
    offset = 0
    while True:
        page = service.get_catalog_snapshot(include_entries=True, limit=100, offset=offset)
        seen.extend(page["entries"])
        if not page["pagination"]["has_more"]:
            break
        offset += len(page["entries"])
    assert len(seen) == 1155
    assert len({entry["id"] for entry in seen}) == 1155


def test_snapshot_pagination_validates_bounds(service_env):
    service, _, _ = service_env
    with pytest.raises(InvalidRequest):
        service.get_catalog_snapshot(include_entries=True, limit=0)
    with pytest.raises(InvalidRequest):
        service.get_catalog_snapshot(include_entries=True, limit=101)
    with pytest.raises(InvalidRequest):
        service.get_catalog_snapshot(include_entries=True, offset=-1)


def test_search_pagination_metadata(service_env):
    service, _, _ = service_env
    page = service.search_strategy_catalog("", limit=3, offset=100)
    assert page["total"] >= 1155
    assert page["offset"] == 100
    assert page["has_more"] is True
    assert len(page["entries"]) == 3
    tail = service.search_strategy_catalog("", limit=10, offset=page["total"] - 5)
    assert len(tail["entries"]) == 5
    assert tail["has_more"] is False


def test_search_empty_result_has_actionable_guidance(service_env):
    service, _, _ = service_env
    result = service.search_strategy_catalog("zzzznopequerty", limit=5)
    assert result["entries"] == []
    assert result["total"] == 0
    assert result["has_more"] is False
    suggestions = result["suggestions"]
    assert "hint" in suggestions
    assert set(suggestions["valid_archetypes"]) == set(ARCHETYPES)


def test_search_unknown_archetype_enumerates_valid_values(service_env):
    service, _, _ = service_env
    with pytest.raises(InvalidRequest, match="valid archetypes"):
        service.search_strategy_catalog("", archetype="nope")
