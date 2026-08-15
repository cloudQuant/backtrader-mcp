# Drafts and validation

## Scaffolds

`create_strategy_draft` renders one of seven archetypes
(`single_data_indicator`, `multi_indicator_system`,
`multi_asset_allocation`, `multi_timeframe`, `pairs_spread`, `order_risk`,
`precomputed_ml`) in one of two output profiles (`single_test`,
`python_bundle`). `precomputed_ml` fails fast unless the first feed declares
at least one custom feature line — it never silently degrades to a baseline
SMA strategy. Generated templates include `notify_order` behind an inert
`record_fills` switch.

## Updates

`update_strategy_draft` requires the current revision and exact file hash
(optimistic concurrency); `get_strategy_draft` returns every file with its
hash.

## Static validation

`validate_strategy_draft` parses and compiles the AST without importing the
candidate in the server, and issues an exact hash-bound validation
capability. Direct Strategy classes are treated separately from cooperative
Indicator/LineIterator/Observer/Analyzer objects (a direct Strategy has no
global `super().__init__()` requirement; a custom cooperative line object
does). `validate_strategy_spec` canonicalizes the StrategySpec against its
immutable dataset without creating any state.

## StrategySpec extensions

- `extensions.analyzers` — an allowlisted subset of `sqn`, `calmar`, `vwr`,
  `timereturn`; their typed metrics land in the result's `extra_metrics`.
- `seed` — an optional canonical integer (0..2^32-1) frozen into the run
  manifest and applied to the candidate's random/numpy state.
