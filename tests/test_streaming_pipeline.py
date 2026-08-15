from __future__ import annotations

import csv
import io
import threading
from pathlib import Path

import pytest

import backtrader_mcp.data as data_module
from backtrader_mcp.errors import InvalidRequest
from backtrader_mcp.state import StateStore

COLUMN_MAP = {
    "datetime": "datetime",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def _legacy_encode(fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_streamed_registration_is_byte_identical_to_legacy(service_env):
    service, source, _ = service_env
    path = source / "prices.csv"
    # Legacy algorithm reference output.
    text = path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(text[: 64 * 1024], delimiters=",;\t|")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    legacy_rows = []
    for row in reader:
        legacy_rows.append(
            {
                "datetime": data_module._datetime(row["datetime"]),
                "open": data_module._number(row["open"], "open"),
                "high": data_module._number(row["high"], "high"),
                "low": data_module._number(row["low"], "low"),
                "close": data_module._number(row["close"], "close"),
                "volume": data_module._number(row["volume"], "volume"),
                "openinterest": "0",
            }
        )
    legacy_bytes = _legacy_encode(list(data_module.BASE_COLUMNS), legacy_rows)

    manifest = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    cas_path = service.settings.state_root / manifest["extensions"]["cas_relative_path"]
    assert cas_path.read_bytes() == legacy_bytes
    assert manifest["extensions"]["content_sha256"] == data_module.sha256_bytes(legacy_bytes)
    assert manifest["extensions"]["row_count"] == len(legacy_rows)


def test_second_registration_reuses_source_level_dedup(service_env, monkeypatch):
    service, source, _ = service_env
    first = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    calls = []
    original = service.datasets._stream_canonical

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.datasets, "_stream_canonical", counting)
    second = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    assert calls == []
    assert (
        second["extensions"]["feed_objects"]["primary"]["sha256"]
        == first["extensions"]["feed_objects"]["primary"]["sha256"]
    )


def test_register_detects_source_change_after_read(service_env, monkeypatch):
    service, source, _ = service_env
    # The streamed registration performs exactly one post-parse hash check;
    # simulate the source changing between read and that check.
    monkeypatch.setattr(data_module, "file_hash", lambda path: "0" * 64)
    with pytest.raises(InvalidRequest, match="source changed"):
        service.register_dataset("market", "prices.csv", COLUMN_MAP)


def test_alignment_streams_each_feed_once(service_env, monkeypatch):
    from backtrader_mcp.util import sha256_json

    service, source, _ = service_env
    (source / "secondary.csv").write_bytes((source / "prices.csv").read_bytes())
    core = {
        "schema_version": "data-spec-v1",
        "feeds": [
            {
                "name": name,
                "role": role,
                "symbol": name.upper(),
                "source": {
                    "root_id": "market",
                    "relative_path": relative_path,
                    "source_type": "local_file",
                },
                "format": "generic_csv",
                "timeframe": "days",
                "compression": 1,
                "timezone": "UTC",
                "columns": COLUMN_MAP,
            }
            for name, role, relative_path in (
                ("primary", "execution", "prices.csv"),
                ("secondary", "signal", "secondary.csv"),
            )
        ],
        "master_feed": "primary",
        "alignment": {"mode": "intersection", "minimum_overlap": 1.0},
        "transforms": [],
    }
    spec = {**core, "spec_hash": sha256_json(core)}
    opens = []
    original_open = Path.open

    def counting_open(self, *args, **kwargs):
        if str(self).endswith(".csv") and "cas" in str(self):
            opens.append(str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    dataset = service.register_local_dataset(spec)
    assert dataset["provenance"]["observed_overlap"] == 1.0
    # CAS opens: one dedup-store verification (file_hash), then exactly one
    # alignment read for the master set and one streamed read for the other
    # feed. A full per-feed set materialization would add a third alignment
    # read for the master feed itself.
    cas_opens = [item for item in opens if "cas" in item]
    assert len(cas_opens) == 3, cas_opens


def test_derive_output_size_cap(service_env, monkeypatch):
    from dataclasses import replace

    service, source, _ = service_env
    manifest = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    monkeypatch.setattr(
        service.datasets, "settings", replace(service.settings, max_dataset_bytes=200)
    )
    with pytest.raises(InvalidRequest, match="exceeds"):
        service.derive_tabular_dataset(
            manifest["dataset_id"], "identity", {}, manifest["manifest_hash"]
        )


def test_derive_bad_value_reports_row_number(service_env, monkeypatch):
    service, source, _ = service_env
    manifest = service.register_dataset("market", "prices.csv", COLUMN_MAP)
    # Corrupt the CAS file and fake the integrity gate to exercise the guard.
    cas_path = service.settings.state_root / manifest["extensions"]["cas_relative_path"]
    corrupt = Path(cas_path.parent / "corrupt.csv")
    lines = cas_path.read_text(encoding="utf-8").splitlines()
    lines[10] = lines[10].replace(lines[10].split(",")[4], "NOT_A_NUMBER")
    corrupt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        service.datasets,
        "_content_path",
        lambda dataset: corrupt,
    )
    with pytest.raises(InvalidRequest, match="row 10"):
        service.derive_tabular_dataset(
            manifest["dataset_id"],
            "returns",
            {"column": "close", "output": "close_ret"},
            manifest["manifest_hash"],
        )


def test_state_store_reuses_connection_per_thread(tmp_path):
    (tmp_path / "state").mkdir()
    store = StateStore(tmp_path / "state")
    first = store.connect()
    assert store.connect() is first
    results: list[bool] = []

    def probe():
        results.append(store.connect() is not first)

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join()
    assert results == [True]


def test_refresh_reuses_fingerprints_and_drops_stale_entries(tmp_path):
    from backtrader_mcp.service import BacktraderMCPService
    from backtrader_mcp.settings import Settings as ServiceSettings

    target = tmp_path / "target"
    state = tmp_path / "state"
    target.mkdir()
    strategy = target / "example_strategy.py"
    strategy.write_text(
        "import backtrader as bt\nclass Example(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    service = BacktraderMCPService(
        ServiceSettings(
            state_root=state, source_roots={}, target_roots={"strategies": target}, runtimes={}
        )
    )
    first = service.refresh_strategy_catalog("strategies")
    assert first["entry_count"] == 1
    import backtrader_mcp.catalog as catalog_module

    hash_calls = []
    original = catalog_module.file_hash

    def counting(path):
        hash_calls.append(str(path))
        return original(path)

    monkeypatch2 = pytest.MonkeyPatch()
    monkeypatch2.setattr(catalog_module, "file_hash", counting)
    second = service.refresh_strategy_catalog("strategies")
    monkeypatch2.undo()
    assert hash_calls == [], hash_calls
    assert second["snapshot_hash"] == first["snapshot_hash"]
    # Removing the source file drops its catalog entry on the next refresh.
    strategy.unlink()
    third = service.refresh_strategy_catalog("strategies")
    assert third["entry_count"] == 0
    assert service.state.list("catalog_entry") == []


def test_search_excludes_stale_entries_after_refresh(tmp_path):
    from backtrader_mcp.service import BacktraderMCPService
    from backtrader_mcp.settings import Settings as ServiceSettings

    target = tmp_path / "target"
    state = tmp_path / "state"
    target.mkdir()
    strategy = target / "gone_strategy.py"
    strategy.write_text(
        "import backtrader as bt\nclass Gone(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    service = BacktraderMCPService(
        ServiceSettings(
            state_root=state, source_roots={}, target_roots={"strategies": target}, runtimes={}
        )
    )
    service.refresh_strategy_catalog("strategies")
    assert service.search_strategy_catalog("gone", limit=5)["total"] == 1
    strategy.unlink()
    service.refresh_strategy_catalog("strategies")
    assert service.search_strategy_catalog("gone", limit=5)["total"] == 0
