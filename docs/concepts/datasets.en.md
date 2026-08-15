# Datasets and adapters

## Immutable content-addressed storage

`register_dataset` normalizes a confined source CSV into a canonical immutable
CSV (datetime strictly increasing, `_number` normalization, UTF-8) and stores
it in the CAS keyed by its content sha256. Identical sources with identical
mapping parameters are deduplicated without re-parsing, and registration
fails if the source changes while being read.

## Typed adapters

`register_local_dataset` accepts a hash-bound DataSpec with 1-32 feeds in six
formats: `generic_csv`, `backtrader_csv`, `yahoo_csv`, `mt5_csv`, `pandas`,
and `pandas_custom_lines`. The controlled worker constructs the named
Backtrader adapter per feed — nothing is silently routed through
`GenericCSVData`.

- Pandas inputs must be materialized `.csv` files
  (`source_type=materialized_dataframe`); pickles and caller-supplied
  constructors are rejected.
- `pandas_custom_lines` requires every custom line in both `lines` and
  `columns`.
- MT5 feeds reject sub-minute timeframes (the adapter would silently
  truncate precision).
- `alignment.mode` accepts only `intersection`; feeds must satisfy the typed
  `minimum_overlap` fraction of the master feed's timestamps.

## Data-quality gate

Registration rejects non-positive OHLC prices and inconsistent bars (high
below low, high below max(open, close), low above min(open, close)) with
row-numbered errors. Markets with legitimate zero/negative prices opt out per
feed with `adapter_options.allow_non_positive_prices=true`; consistency is
always enforced.

## Bar operations

Each feed may declare `extensions.bar_operation`:

```json
{"mode": "direct"}
```

```json
{"mode": "resample", "timeframe": "minutes", "compression": 5}
```

`replay` is also supported. Resample/replay are applied with
`Cerebro.resampledata` / `Cerebro.replaydata`; successful fixed-test results
record per-mode `feed_runtime` evidence (requested format, actual adapter
class, bar operation, source row count, output bar count). The CloudQuant
fork resamples with `bar2edge=True` by default — unlike upstream backtrader.

## Derivation

`derive_tabular_dataset` runs `identity`, `dropna`, `returns`, or `sma` with
typed parameters and an exact source-manifest hash. `returns`/`sma` drop
their warmup rows (1 for returns, `period-1` for sma) and register the
derived column as a `pandas_custom_lines` feature line, so derived datasets
feed `precomputed_ml` strategies directly. Outputs are capped at the
configured `max_dataset_bytes`.
