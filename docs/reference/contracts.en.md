# Contracts and policies

## JSON Schema contracts

The wheel ships seven JSON Schema 2020-12 contracts (readable via the
`backtrader-mcp://contracts/{schema_name}` resource):

- `strategy-spec` — typed strategy intent (archetype, feeds, parameters,
  sizing, risk, run modes, allowed imports, analyzers, seed).
- `dataset-manifest` — immutable dataset manifest with the embedded
  `DataSpec` definition.
- `corpus-manifest` — catalog snapshot header and projected entries.
- `artifact-manifest` — the hash-bound draft artifact.
- `validation-report` — AST validation findings by object category.
- `run-manifest` — the frozen run fingerprint (engine commit, environment
  hash with pandas/numpy, profile, seed, analyzers, approval id).
- `run-result` — normalized metrics, feed runtime evidence, extras.

## Comparison policy

`comparison-profile-v1` is the single authority for run comparison:
six integer metrics compare exactly, five float metrics use
`default_float_tolerance` (rel 1e-7, abs 1e-9) with a tightened
`final_value` override (rel 1e-9, abs 1e-6), nullability is explicit, and
non-finite values fail comparison. The comparison code loads this file at
runtime, and tests assert the two never drift.

## Execution semantics

- Default sizer: `FixedSize(stake=1)` — `self.buy()` trades one unit.
- Commission: fixed percentage, both sides (`percabs=True`).
- No cheat-on-close: market orders fill at the next bar's open.
- Sharpe: risk-free rate 0.01, population stddev, timeframe-derived
  annualization (252/52/12).
- `max_drawdown` is reported as a positive percent.
- yahoo adapter stores raw close (`adjclose=False`).
