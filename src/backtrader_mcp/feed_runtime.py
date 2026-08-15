"""Trusted construction of typed feeds from immutable canonical CSV objects."""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import backtrader as bt
from backtrader import feeds as bt_feeds
from backtrader.analyzers.drawdown import DrawDown
from backtrader.analyzers.returns import Returns
from backtrader.analyzers.sharpe import SharpeRatio
from backtrader.analyzers.tradeanalyzer import TradeAnalyzer
from backtrader.feeds.btcsv import BacktraderCSVData
from backtrader.feeds.csvgeneric import GenericCSVData

# ``MT4CSVData`` imports ``GenericCSVData`` through ``backtrader.feeds``.
# CloudQuant's light import mode intentionally leaves that package namespace
# minimal, so publish the one core adapter it requires before loading MT4.
if not hasattr(bt_feeds, "GenericCSVData"):
    setattr(bt_feeds, "GenericCSVData", GenericCSVData)

from backtrader.feeds.mt4csv import MT4CSVData
from backtrader.feeds.pandafeed import PandasData
from backtrader.feeds.yahoo import YahooFinanceCSVData

TIMEFRAMES = {
    "ticks": bt.TimeFrame.Ticks,
    "microseconds": bt.TimeFrame.MicroSeconds,
    "seconds": bt.TimeFrame.Seconds,
    "minutes": bt.TimeFrame.Minutes,
    "days": bt.TimeFrame.Days,
    "weeks": bt.TimeFrame.Weeks,
    "months": bt.TimeFrame.Months,
    "years": bt.TimeFrame.Years,
}


def _canonical_rows(path: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("materialized canonical CSV has no rows")
    return rows


def _adapter_csv_file(header: list[str], rows: list[list[str]]) -> Path:
    """Materialize an adapter-specific CSV for Backtrader feeds requiring paths."""

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix="backtrader-mcp-feed-",
            suffix=".csv",
            delete=False,
        ) as stream:
            path = Path(stream.name)
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        return path
    except BaseException:
        if path is not None:
            path.unlink(missing_ok=True)
        raise


def _remove_adapter_files(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _timeframe(config: dict[str, Any]) -> int:
    try:
        return TIMEFRAMES[config["source_timeframe"]]
    except KeyError as exc:
        raise ValueError("unknown materialized source timeframe") from exc


def _build_feed(config: dict[str, Any]) -> tuple[Any, int, list[Path]]:
    path = config["canonical_csv_path"]
    source_timeframe = _timeframe(config)
    compression = config["source_compression"]
    input_format = config["input_format"]
    rows = _canonical_rows(path)
    common = {"timeframe": source_timeframe, "compression": compression}
    adapter_files: list[Path] = []
    try:
        if input_format in {"generic_csv", "canonical_csv_v1"}:
            feed = GenericCSVData(
                dataname=path,
                dtformat="%Y-%m-%dT%H:%M:%S",
                datetime=0,
                open=1,
                high=2,
                low=3,
                close=4,
                volume=5,
                openinterest=6,
                headers=True,
                **common,
            )
        elif input_format == "backtrader_csv":
            adapter_path = _adapter_csv_file(
                ["date", "time", "open", "high", "low", "close", "volume", "openinterest"],
                [
                    [
                        row["datetime"][:10],
                        row["datetime"][11:19],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        row["openinterest"],
                    ]
                    for row in rows
                ],
            )
            adapter_files.append(adapter_path)
            feed = BacktraderCSVData(dataname=str(adapter_path), headers=True, **common)
        elif input_format == "yahoo_csv":
            adapter_path = _adapter_csv_file(
                ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"],
                [
                    [
                        row["datetime"][:10],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["close"],
                        row["volume"],
                    ]
                    for row in rows
                ],
            )
            adapter_files.append(adapter_path)
            feed = YahooFinanceCSVData(
                dataname=str(adapter_path),
                headers=True,
                reverse=False,
                adjclose=False,
                round=False,
                **common,
            )
        elif input_format == "mt5_csv":
            adapter_path = _adapter_csv_file(
                ["date", "time", "open", "high", "low", "close", "volume"],
                [
                    [
                        row["datetime"][:10].replace("-", "."),
                        row["datetime"][11:16],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                    ]
                    for row in rows
                ],
            )
            adapter_files.append(adapter_path)
            # Backtrader's MT4CSVData is also the controlled adapter for MT5's
            # compatible date/time/OHLCV export shape.
            feed = MT4CSVData(dataname=str(adapter_path), headers=True, **common)
        elif input_format in {"pandas", "pandas_custom_lines"}:
            import pandas as pd

            frame = pd.read_csv(path)
            frame["datetime"] = pd.to_datetime(frame["datetime"], errors="raise")
            frame = frame.set_index("datetime")
            feed_class: type[Any] = PandasData
            custom_lines = tuple(config.get("custom_lines", ()))
            if input_format == "pandas_custom_lines":
                if not custom_lines:
                    raise ValueError("pandas_custom_lines has no declared custom lines")
                feed_class = type(
                    "MaterializedPandasCustomLines",
                    (PandasData,),
                    {
                        "lines": custom_lines,
                        "params": tuple((line, line) for line in custom_lines),
                    },
                )
            feed = feed_class(
                dataname=frame,
                datetime=None,
                open="open",
                high="high",
                low="low",
                close="close",
                volume="volume",
                openinterest="openinterest",
                **common,
            )
        else:
            raise ValueError(f"unsupported materialized feed format: {input_format}")
        return feed, len(rows), adapter_files
    except BaseException:
        _remove_adapter_files(adapter_files)
        raise


def _validate_frozen_paths(feed_configs: list[dict[str, Any]]) -> None:
    frozen_configs = json.loads(os.environ["BACKTRADER_MCP_FEEDS_JSON"])
    if type(feed_configs) is not list or any(type(config) is not dict for config in feed_configs):
        raise ValueError("feed configs must be plain JSON objects")
    if feed_configs != frozen_configs:
        raise ValueError("feed configs do not match the worker-frozen configuration")
    raw_paths = json.loads(os.environ["BACKTRADER_MCP_DATASETS_JSON"])
    if type(raw_paths) is not dict or any(
        type(name) is not str or type(path) is not str for name, path in raw_paths.items()
    ):
        raise ValueError("worker dataset path binding is invalid")
    seen: set[str] = set()
    for config in feed_configs:
        name = config.get("name")
        path = config.get("canonical_csv_path")
        if (
            not isinstance(name, str)
            or name in seen
            or not isinstance(path, str)
            or raw_paths.get(name) != path
        ):
            raise ValueError("feed config does not match the worker-frozen dataset paths")
        seen.add(name)


def _add_feed(
    cerebro: Any,
    feed: Any,
    strategy_name: str,
    operation: dict[str, Any],
) -> Any:
    mode = operation["mode"]
    if mode == "direct":
        return cerebro.adddata(feed, name=strategy_name)
    kwargs = {
        "timeframe": TIMEFRAMES[operation["timeframe"]],
        "compression": operation["compression"],
    }
    if mode == "resample":
        return cerebro.resampledata(feed, name=strategy_name, **kwargs)
    if mode == "replay":
        return cerebro.replaydata(feed, name=strategy_name, **kwargs)
    raise ValueError("unknown bar operation")


_EXTRA_ANALYZER_FACTORIES = {
    "sqn": ("backtrader.analyzers.sqn", "SQN"),
    "calmar": ("backtrader.analyzers.calmar", "Calmar"),
    "vwr": ("backtrader.analyzers.vwr", "VWR"),
    "timereturn": ("backtrader.analyzers.timereturn", "TimeReturn"),
}


def _apply_seed() -> None:
    raw = os.environ.get("BACKTRADER_MCP_SEED")
    if not raw:
        return
    try:
        seed = int(raw)
    except ValueError:
        return
    import random

    random.seed(seed)
    try:
        import numpy

        numpy.random.seed(seed)
    except ImportError:
        pass


def _add_extra_analyzers(cerebro: Any) -> list[str]:
    raw = os.environ.get("BACKTRADER_MCP_ANALYZERS", "[]")
    try:
        names = json.loads(raw)
    except json.JSONDecodeError:
        names = []
    for name in names:
        factory = _EXTRA_ANALYZER_FACTORIES.get(name)
        if factory is None:
            continue
        module_name, class_name = factory
        module = __import__(module_name, fromlist=[class_name])
        analyzer_class = getattr(module, class_name)
        cerebro.addanalyzer(analyzer_class, _name=f"extra_{name}")
    return [name for name in names if name in _EXTRA_ANALYZER_FACTORIES]


def _extra_analyzer_metrics(strategy: Any, names: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for name in names:
        analyzer = getattr(strategy.analyzers, f"extra_{name}", None)
        if analyzer is None:
            continue
        analysis = analyzer.get_analysis()
        if name == "timereturn":
            values = analysis.values() if hasattr(analysis, "values") else []
            metrics["time_return"] = float(list(values)[-1]) if values else None
        elif isinstance(analysis, dict) and analysis:
            metric_name = {"sqn": "sqn", "calmar": "calmar", "vwr": "vwr"}[name]
            value = analysis.get(metric_name)
            metrics[metric_name] = _finite_or_none(value)
    return metrics


def _count(trades: Any, section: str) -> int:
    value = trades.get(section, {}).get("total")
    return int(value) if isinstance(value, (int, float)) else 0


def _finite_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def run_materialized_backtest(
    strategy_class: type[Any],
    feed_configs: list[dict[str, Any]],
    feed_bindings: list[dict[str, str]],
    *,
    starting_cash: float,
    commission: float,
    run_mode: str,
    archetype: str,
    slippage: float = 0.0,
) -> dict[str, Any]:
    """Run a generated strategy using only worker-verified materialized inputs."""

    _validate_frozen_paths(feed_configs)
    _apply_seed()
    configs = {config["name"]: config for config in feed_configs}
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(commission=commission)
    if slippage > 0:
        cerebro.broker.set_slippage_fixed(slippage)
    adapter_files: list[Path] = []
    try:
        runtime_evidence: list[dict[str, Any]] = []
        for binding in feed_bindings:
            config = configs[binding["dataset_feed"]]
            feed, source_row_count, created_files = _build_feed(config)
            adapter_files.extend(created_files)
            operation = config["bar_operation"]
            added = _add_feed(cerebro, feed, binding["strategy_name"], operation)
            runtime_evidence.append(
                {
                    "dataset_feed": config["name"],
                    "strategy_feed": binding["strategy_name"],
                    "input_format": config["input_format"],
                    "adapter": config["adapter"],
                    "constructed_class": type(feed).__name__,
                    "bar_operation": operation,
                    "source_row_count": source_row_count,
                    "registered_class": type(added).__name__,
                }
            )
        params_override = json.loads(os.environ.get("BACKTRADER_MCP_PARAMS", "{}"))
        cerebro.addstrategy(strategy_class, **params_override)
        cerebro.addanalyzer(SharpeRatio, _name="sharpe")
        cerebro.addanalyzer(Returns, _name="returns")
        cerebro.addanalyzer(DrawDown, _name="drawdown")
        cerebro.addanalyzer(TradeAnalyzer, _name="trades")
        extra_analyzer_names = _add_extra_analyzers(cerebro)
        strategies = cerebro.run(runonce=run_mode == "runonce")
        strategy = strategies[0]
        trades = strategy.analyzers.trades.get_analysis()
        sharpe = strategy.analyzers.sharpe.get_analysis().get("sharperatio")
        returns = strategy.analyzers.returns.get_analysis()
        drawdown = strategy.analyzers.drawdown.get_analysis()
        final_value = float(cerebro.broker.getvalue())
        for evidence, data in zip(runtime_evidence, cerebro.datas):
            evidence["output_bar_count"] = int(data.buflen())
        metrics = {
            "bar_num": int(len(strategy)),
            "buy_count": _count(trades, "long"),
            "sell_count": _count(trades, "short"),
            "win_count": _count(trades, "won"),
            "loss_count": _count(trades, "lost"),
            "trade_num": _count(trades, "total"),
            "final_value": _finite_or_none(final_value),
            "sharpe_ratio": _finite_or_none(sharpe),
            "annual_return": _finite_or_none(returns.get("rnorm")),
            "max_drawdown": _finite_or_none(drawdown.get("max", {}).get("drawdown")),
            "return_rate": _finite_or_none((final_value / starting_cash - 1.0) * 100.0),
        }
        return {
            "schema_version": "run-result-v1",
            "run_mode": run_mode,
            "archetype": archetype,
            "metrics": {
                **metrics,
                **_extra_analyzer_metrics(strategy, extra_analyzer_names),
            },
            "feed_runtime": runtime_evidence,
        }
    finally:
        _remove_adapter_files(adapter_files)
