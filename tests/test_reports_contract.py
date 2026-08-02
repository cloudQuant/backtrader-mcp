from __future__ import annotations

import math

import pytest

from backtrader_mcp.errors import InvalidRequest
from backtrader_mcp.reports import compare_metrics, normalize_metrics, render_markdown


def canonical_metrics(**overrides: object) -> dict[str, object]:
    metrics: dict[str, object] = {
        "bar_num": 120,
        "buy_count": 4,
        "sell_count": 4,
        "win_count": 3,
        "loss_count": 1,
        "trade_num": 4,
        "final_value": 101_250.5,
        "sharpe_ratio": 1.25,
        "annual_return": 0.12,
        "max_drawdown": 4.5,
        "return_rate": 1.25,
    }
    metrics.update(overrides)
    return metrics


def test_normalize_metrics_preserves_contractual_values_and_numeric_extras():
    normalized = normalize_metrics(
        canonical_metrics(
            sharpe_ratio=None,
            annual_return=None,
            custom_score=2,
            ignored_boolean=True,
            ignored_text="not a metric",
        )
    )

    assert normalized["final_value"] == 101_250.5
    assert normalized["sharpe_ratio"] is None
    assert normalized["annual_return"] is None
    assert normalized["_extra_metrics"] == {"custom_score": 2.0}


@pytest.mark.parametrize(
    ("metrics", "message"),
    [
        ({}, "11 canonical fields"),
        (canonical_metrics(bar_num=-1), "bar_num must be a non-negative integer"),
        (canonical_metrics(bar_num=True), "bar_num must be a non-negative integer"),
        (canonical_metrics(final_value=math.nan), "final_value must be finite"),
        (canonical_metrics(max_drawdown=math.inf), "max_drawdown must be finite"),
        (canonical_metrics(return_rate=None), "return_rate must be finite"),
    ],
)
def test_normalize_metrics_rejects_invalid_contract_values(
    metrics: dict[str, object], message: str
):
    with pytest.raises(InvalidRequest, match=message):
        normalize_metrics(metrics)


def test_compare_metrics_has_stable_match_hash_for_identical_results():
    metrics = canonical_metrics()

    first = compare_metrics(metrics, metrics)
    second = compare_metrics(metrics, metrics)

    assert first["status"] == "matched"
    assert first["diagnostics"] == []
    assert first["comparison_hash"] == second["comparison_hash"]


@pytest.mark.parametrize(
    ("left", "right", "metric", "code"),
    [
        (canonical_metrics(trade_num=2), canonical_metrics(), "trade_num", "exact_mismatch"),
        (
            canonical_metrics(sharpe_ratio=None),
            canonical_metrics(),
            "sharpe_ratio",
            "null_mismatch",
        ),
        (
            canonical_metrics(final_value=101_260.0),
            canonical_metrics(),
            "final_value",
            "float_mismatch",
        ),
    ],
)
def test_compare_metrics_reports_standard_metric_mismatches(
    left: dict[str, object], right: dict[str, object], metric: str, code: str
):
    comparison = compare_metrics(left, right, rel_tol=0.0, abs_tol=0.0)

    assert comparison["status"] == "mismatched"
    assert comparison["diagnostics"][0]["metric"] == metric
    assert comparison["diagnostics"][0]["code"] == code


def test_compare_metrics_respects_float_tolerance():
    comparison = compare_metrics(
        canonical_metrics(final_value=101_250.5000001),
        canonical_metrics(),
        rel_tol=1e-7,
        abs_tol=1e-9,
    )

    assert comparison["status"] == "matched"


def test_compare_metrics_rejects_extra_metric_present_on_only_one_side():
    comparison = compare_metrics(
        canonical_metrics(custom_score=0.75),
        canonical_metrics(),
    )

    assert comparison["status"] == "mismatched"
    assert comparison["diagnostics"] == [
        {
            "metric": "custom_score",
            "code": "null_mismatch",
            "left": 0.75,
            "right": None,
        }
    ]


def test_render_markdown_renders_canonical_extra_and_diagnostic_content():
    result = {
        "run_id": "job_example",
        "status": "SUCCEEDED",
        "result_hash": "abc123",
        "metrics": canonical_metrics(custom_score=0.75),
        "diagnostics": [{"code": "warning"}],
    }

    rendered = render_markdown(result)

    assert "# Backtrader MCP run report" in rendered
    assert "| annual_return (ratio) | 0.12 |" in rendered
    assert "| max_drawdown (percent) | 4.5 |" in rendered
    assert "## Extra metrics" in rendered
    assert "- custom_score: 0.75" in rendered
    assert "- Count: 1" in rendered
    assert rendered.endswith("\n")
