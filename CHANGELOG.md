# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-01

### Added
- Contract-compatible extensions for `strategy-spec-v1` and `run-result-v1`:
  optional `extra_metrics` under run-result extensions, an allowlisted
  `allowed_imports` superset, non-empty `run_modes` subsets, and a `slippage`
  field. Backward compatible; existing specs and results remain valid.
- Subprocess resource limits (CPU, memory, file size, process count) for the
  controlled worker and candidate runs.
- Job concurrency cap (`max_concurrent_jobs`) and tunable resource env vars.
- Structured logging via `BACKTRADER_MCP_LOG_LEVEL`.
- CLI subcommands: `list`, `logs`, `clean`, `show`.
- Doctor issue `suggestion` field and sanitized client-facing error messages.
- CI workflow, coverage gating (`fail_under = 80`), ruff lint, mypy config,
  pre-commit hooks, `CHANGELOG.md`, `CONTRIBUTING.md`.

### Changed
- Dependency bounds widened: `mcp>=2.0.0,<3` and `pandas>=2.0,<3`.
- Worker heartbeat write frequency reduced from 10 Hz to ~1 Hz.

## [0.1.0] - 2026-07-31

### Added
- Initial independent P0 release: local-first MCP server for reproducible
  Backtrader strategy development. Offline, backtest-only.
- Immutable content-addressed CSV datasets, private strategy drafts, AST
  validation without server-side import, HMAC hash-bound tokens, distinct
  local CLI approvals, journaled apply, durable subprocess jobs with status,
  cancel, timeout, recovery, normalized reports, and run comparison.
- Seven JSON Schema 2020-12 contracts, `comparison-profile-v1`, six typed
  data adapters, four host configurations, and a bundled strategy catalog.
