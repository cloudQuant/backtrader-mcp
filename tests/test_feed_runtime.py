"""Regression coverage for trusted Backtrader feed construction."""

from __future__ import annotations

import json
from pathlib import Path

import backtrader as bt
import pytest

import backtrader_mcp.feed_runtime as feed_runtime
from backtrader_mcp.data import INPUT_FORMAT_ADAPTERS


class _PassiveStrategy(bt.Strategy):
    pass


class _FailingStrategy(bt.Strategy):
    def next(self):
        raise RuntimeError("intentional feed runtime failure")


def _canonical_csv(tmp_path: Path) -> Path:
    path = tmp_path / "canonical.csv"
    rows = ["datetime,open,high,low,close,volume,openinterest"]
    for index in range(20):
        close = 100 + index
        rows.append(
            f"2023-01-{index + 1:02d}T09:30:00,{close - 1},{close + 1},{close - 2},"
            f"{close},{1000 + index},0"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _feed_config(path: Path, input_format: str) -> dict[str, object]:
    return {
        "name": "primary",
        "canonical_csv_path": str(path),
        "source_timeframe": "days",
        "source_compression": 1,
        "input_format": input_format,
        "custom_lines": [],
        "bar_operation": {"mode": "direct"},
        "adapter": INPUT_FORMAT_ADAPTERS[input_format],
    }


def _freeze_feed_config(
    monkeypatch: pytest.MonkeyPatch,
    config: dict[str, object],
) -> None:
    monkeypatch.setenv("BACKTRADER_MCP_FEEDS_JSON", json.dumps([config]))
    monkeypatch.setenv(
        "BACKTRADER_MCP_DATASETS_JSON",
        json.dumps({"primary": config["canonical_csv_path"]}),
    )


def _capture_adapter_files(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    created: list[Path] = []
    original = feed_runtime._adapter_csv_file

    def record(header: list[str], rows: list[list[str]]) -> Path:
        path = original(header, rows)
        created.append(path)
        return path

    monkeypatch.setattr(feed_runtime, "_adapter_csv_file", record)
    return created


@pytest.mark.parametrize("input_format", ["backtrader_csv", "yahoo_csv", "mt5_csv"])
def test_path_backed_csv_adapters_are_removed_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    input_format: str,
):
    config = _feed_config(_canonical_csv(tmp_path), input_format)
    _freeze_feed_config(monkeypatch, config)
    created = _capture_adapter_files(monkeypatch)

    result = feed_runtime.run_materialized_backtest(
        _PassiveStrategy,
        [config],
        [{"dataset_feed": "primary", "strategy_name": "primary"}],
        starting_cash=100_000.0,
        commission=0.001,
        run_mode="runonce",
        archetype="test",
    )

    assert result["feed_runtime"][0]["constructed_class"]
    assert len(created) == 1
    assert not created[0].exists()


def test_path_backed_csv_adapter_is_removed_after_strategy_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = _feed_config(_canonical_csv(tmp_path), "backtrader_csv")
    _freeze_feed_config(monkeypatch, config)
    created = _capture_adapter_files(monkeypatch)

    with pytest.raises(RuntimeError, match="intentional feed runtime failure"):
        feed_runtime.run_materialized_backtest(
            _FailingStrategy,
            [config],
            [{"dataset_feed": "primary", "strategy_name": "primary"}],
            starting_cash=100_000.0,
            commission=0.001,
            run_mode="runnext",
            archetype="test",
        )

    assert len(created) == 1
    assert not created[0].exists()
