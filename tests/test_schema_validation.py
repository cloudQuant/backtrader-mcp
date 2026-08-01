"""JSON Schema rejection tests for the shipped contract schemas."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "src" / "backtrader_mcp" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _valid_strategy_spec() -> dict:
    return {
        "spec_version": "strategy-spec-v1",
        "name": "test",
        "slug": "test",
        "category": "strategy",
        "archetype": "single_data_indicator",
        "output_profile": "single_test",
        "dataset_id": "ds_" + "a" * 64,
        "feeds": [
            {
                "name": "primary",
                "role": "execution",
                "symbol": "X",
                "timeframe": "days",
                "lines": ["close"],
            }
        ],
        "parameters": [],
        "entry": {"rule_names": ["r"]},
        "exit": {"rule_names": ["r"]},
        "sizing": {},
        "risk": {},
        "run_modes": ["runonce", "runnext"],
        "allowed_imports": ["backtrader"],
        "spec_hash": "a" * 64,
    }


def test_strategy_spec_valid_passes():
    jsonschema.validate(_valid_strategy_spec(), _load("strategy-spec"))


def test_strategy_spec_bad_archetype_rejected():
    spec = _valid_strategy_spec()
    spec["archetype"] = "not_a_real_archetype"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, _load("strategy-spec"))


def test_strategy_spec_bad_dataset_id_pattern_rejected():
    spec = _valid_strategy_spec()
    spec["dataset_id"] = "not-a-hash"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, _load("strategy-spec"))


def test_strategy_spec_bad_output_profile_rejected():
    spec = _valid_strategy_spec()
    spec["output_profile"] = "notebook"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, _load("strategy-spec"))


def test_strategy_spec_bad_slug_rejected():
    spec = _valid_strategy_spec()
    spec["slug"] = "Not Kebab Case!"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, _load("strategy-spec"))


def _valid_run_result() -> dict:
    return {
        "schema_version": "run-result-v1",
        "run_id": "job_1",
        "status": "passed",
        "metrics": {
            "bar_num": 100,
            "buy_count": 1,
            "sell_count": 1,
            "win_count": 1,
            "loss_count": 0,
            "trade_num": 1,
            "final_value": 100.0,
            "sharpe_ratio": None,
            "annual_return": None,
            "max_drawdown": 0.0,
            "return_rate": 0.0,
        },
        "diagnostics": [],
        "artifacts": [],
        "result_hash": "a" * 64,
    }


def test_run_result_valid_passes():
    jsonschema.validate(_valid_run_result(), _load("run-result"))


def test_run_result_missing_metric_rejected():
    result = _valid_run_result()
    result["metrics"].pop("bar_num")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(result, _load("run-result"))


def test_run_result_bad_metric_type_rejected():
    result = _valid_run_result()
    result["metrics"]["bar_num"] = -1  # minimum is 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(result, _load("run-result"))


def test_run_result_extra_metric_in_extensions():
    result = _valid_run_result()
    result["extensions"] = {"extra_metrics": {"sortino_ratio": 1.5}}
    jsonschema.validate(result, _load("run-result"))
