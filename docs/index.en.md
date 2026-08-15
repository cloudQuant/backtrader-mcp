# Backtrader MCP

Backtrader MCP is an independent, **local-first MCP server** for building and
running reproducible [Backtrader](https://github.com/cloudQuant/backtrader)
strategies. It turns confined CSV files into immutable datasets, typed
strategy intent into private drafts, and reviewed drafts into bounded
subprocess runs with durable status and reports.

The product is deliberately **offline and backtest-only**: no brokers, no
stores, no credentials, no live orders, no arbitrary Python execution, no
network transports.

## Highlights

- **Immutable data**: content-addressed CSV datasets with a data-quality gate
  (OHLC consistency), six typed adapters, resample/replay bar operations,
  streamed derivation (`identity`/`dropna`/`returns`/`sma`) whose feature
  columns feed `precomputed_ml` strategies.
- **Reviewable strategy intent**: seven archetypes × two output profiles,
  AST validation without server-side imports, allowlisted analyzers
  (sqn/calmar/vwr/timereturn), and an optional frozen seed.
- **Human-gated authorization**: HMAC hash-bound tokens with one-time nonces,
  a trusted local approval CLI for both changes and runs, and full audit
  trails with the approver's OS identity.
- **Durable execution**: CAS-guarded job state machine, a server-owned
  watchdog, structured `error_kind` classification, cancellation, timeout,
  crash recovery, `parameter_sweep` grids, and normalized 11-metric reports
  with a policy-driven comparison profile.
- **Observable and operable**: `list_jobs` / `get_run_logs` /
  `list_target_tree`, structured tool errors with `Suggestion:` guidance,
  a read-only `doctor` diagnostic, and retention cleanup for every stored
  object class.

## Quick start

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

Then configure the four root variables and register the server with your MCP
host — see [Installation](getting-started/installation.md) and
[Host setup](getting-started/hosts.md).
