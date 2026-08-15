# Runs, jobs, and sweeps

## The authorization chain

`prepare_strategy_run` freezes the exact draft, artifact, validation, dataset,
runtime (version-file hash + git commit), profile, timeout, seed, analyzers,
and parameter grid into a hash-bound plan and returns a signed run token. A
**separate local approval** (`backtrader-mcp approve --run-plan ... --yes`)
is mandatory before `start_strategy_run`, which consumes the approval and the
token nonce after the durable job row exists.

## Run profiles

| Profile | Modes | Purpose |
|---|---|---|
| `runonce` | runonce | Fast single pass |
| `runnext` | runnext | Incremental pass |
| `runonce_runnext_compare` | runonce, runnext | Determinism gate |
| `fixed_tests` | runonce, runnext | Default; determinism gate |
| `parameter_sweep` | runonce per combination | Typed parameter grid |

`parameter_sweep` freezes a `param_grid` (StrategySpec parameter names to
value lists, at most 64 combinations) under the same single approval.
Parameters are passed through `cerebro.addstrategy(..., **override)`; results
carry a `sweep` block with every combination's metrics ranked by
`return_rate`.

## Job lifecycle

States: `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELLED`, `SUCCEEDED`,
`FAILED`, `TIMED_OUT`, `ORPHANED`. Every transition is a compare-and-swap
write with one arbitration rule: **a terminal state, once persisted, is never
overwritten, and a visible `CANCEL_REQUESTED` suppresses
`SUCCEEDED`/`FAILED`/`TIMED_OUT`**.

A server-owned watchdog (started only by `serve`) consumes the worker
heartbeat, enforces the wall-clock deadline with a grace period, orphans jobs
whose worker died, and cleans up detached candidate process groups. Jobs
report a structured `error_kind`
(`user_strategy`/`resource_limit`/`timeout`/`validation`/`infrastructure`/
`cancelled`/`orphaned`).

The concurrency cap rejects instead of queueing: `start_strategy_run` fails
with an actionable suggestion at `max_concurrent_jobs`.

## Results and comparison

Successful results contain exactly eleven canonical metrics (`bar_num`,
`buy_count`, `sell_count`, `win_count`, `loss_count`, `trade_num`,
`final_value`, `sharpe_ratio`, `annual_return`, `max_drawdown`,
`return_rate`); `sharpe_ratio` and `annual_return` are nullable. The packaged
`comparison-profile-v1` policy is the single authority for comparison
tolerances, including the tightened `final_value` override
(rel 1e-9 / abs 1e-6). Allowlisted analyzer metrics appear under
`extra_metrics`; every run manifest fingerprints the runtime commit and the
resolved pandas/numpy versions.
