from __future__ import annotations

import pytest

from backtrader_mcp.errors import InvalidRequest
from backtrader_mcp.reports import compare_metrics, load_comparison_policy

COLUMN_MAP = {
    "datetime": "datetime",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def _metrics(final_value: float) -> dict:
    return {
        "bar_num": 10,
        "buy_count": 0,
        "sell_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "trade_num": 0,
        "final_value": final_value,
        "sharpe_ratio": None,
        "annual_return": None,
        "max_drawdown": 0.0,
        "return_rate": 0.0,
    }


def test_comparison_uses_policy_metric_overrides():
    policy = load_comparison_policy()
    override = policy["metric_overrides"]["final_value"]
    assert override == {"rel_tol": 1e-9, "abs_tol": 1e-6}
    # 1e-4 apart: matches under the old default rel 1e-7, must mismatch
    # under the policy override (abs 1e-6).
    result = compare_metrics(_metrics(100_000.0), _metrics(100_000.0 + 1e-4))
    assert result["status"] == "mismatched"
    diagnostic = next(item for item in result["diagnostics"] if item["metric"] == "final_value")
    assert diagnostic["absolute_tolerance"] == 1e-6
    # Within the override: matched.
    result = compare_metrics(_metrics(100_000.0), _metrics(100_000.0 + 1e-7))
    assert result["status"] == "matched"
    # Profile surfaces the policy as the single authority.
    assert result["profile"]["metric_overrides"]["final_value"]["abs_tol"] == 1e-6


def test_precomputed_ml_requires_custom_lines(registered_ml_dataset):
    service, dataset = registered_ml_dataset
    from conftest import canonical_spec

    spec = canonical_spec(dataset["dataset_id"], "precomputed_ml")
    # canonical_spec declares the custom line; strip it to exercise fail-fast.
    spec["feeds"][0].pop("lines")
    with pytest.raises(InvalidRequest, match="precomputed_ml requires"):
        service.create_strategy_draft(spec)
    spec["feeds"][0]["lines"] = [
        "datetime", "open", "high", "low", "close", "volume", "openinterest", "signal",
    ]
    draft = service.create_strategy_draft(spec)
    assert draft["archetype"] == "precomputed_ml"


def test_seed_is_canonical_and_frozen_into_run_plans(registered_dataset):
    service, dataset = registered_dataset
    from conftest import canonical_spec

    spec = canonical_spec(dataset["dataset_id"], "single_data_indicator")
    spec["seed"] = 42
    draft = service.create_strategy_draft(spec)
    assert draft["strategy_spec"]["seed"] == 42
    validation = service.validate_strategy_draft(draft["draft_id"], draft["revision"])
    plan = service.prepare_strategy_run(
        draft["draft_id"],
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        20,
        "fixed_tests",
        "seed-freeze",
    )
    assert plan["frozen_inputs"]["seed"] == 42
    assert plan["frozen_inputs"]["runtime_commit"] is not None


def test_analyzer_whitelist_rejects_unknown(registered_dataset):
    service, dataset = registered_dataset
    from conftest import canonical_spec

    spec = canonical_spec(dataset["dataset_id"], "single_data_indicator")
    spec["extensions"] = {"analyzers": ["omega"]}
    with pytest.raises(InvalidRequest, match="analyzers"):
        service.create_strategy_draft(spec)


def test_ohlc_quality_gate_rejects_bad_rows(service_env, monkeypatch):
    service, source, _ = service_env
    bad = source / "bad.csv"
    lines = ["datetime,open,high,low,close,volume"]
    for index in range(5):
        lines.append(f"2023-01-{index + 1:02d},{-1.0},2.0,1.0,1.5,100")
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(InvalidRequest, match="row 2 has non-positive"):
        service.register_dataset("market", "bad.csv", COLUMN_MAP)
    inconsistent = source / "inconsistent.csv"
    lines = ["datetime,open,high,low,close,volume"]
    for index in range(5):
        lines.append(f"2023-02-{index + 1:02d},2.0,3.0,4.0,2.5,100")
    inconsistent.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(InvalidRequest, match="inconsistent OHLC"):
        service.register_dataset("market", "inconsistent.csv", COLUMN_MAP)


def test_analyzer_metrics_flow_into_results(registered_dataset):
    """Declared allowlisted analyzers produce extra metrics in a real backtest."""
    service, dataset = registered_dataset
    from conftest import canonical_spec

    spec = canonical_spec(dataset["dataset_id"], "single_data_indicator")
    spec["extensions"] = {"analyzers": ["sqn", "vwr"]}
    draft = service.create_strategy_draft(spec)
    validation = service.validate_strategy_draft(draft["draft_id"], draft["revision"])
    plan = service.prepare_strategy_run(
        draft["draft_id"],
        validation["validation_token"],
        dataset["dataset_id"],
        "default",
        90,
        "fixed_tests",
        "analyzers-run",
    )
    approval = service.jobs.approve_run_plan(plan["run_plan_id"], plan["run_token"])
    started = service.start_strategy_run(
        plan["run_plan_id"], plan["run_token"], approval["approval_id"], "analyzers-start"
    )
    import time

    job_id = started["job_id"]
    for _ in range(90):
        status = service.get_run_status(job_id)
        if status["state"] in {"SUCCEEDED", "FAILED", "TIMED_OUT", "ORPHANED", "CANCELLED"}:
            break
        time.sleep(1)
    assert status["state"] == "SUCCEEDED", status.get("error")
    result = service.get_run_result(job_id)
    extra = result["extensions"]["extra_metrics"]
    assert extra is not None
    assert "sqn" in extra
    assert "vwr" in extra
