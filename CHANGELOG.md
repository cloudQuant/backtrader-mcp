# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Explicit StrategySpec canonical support for `slippage`, `ir`, `extensions`,
  `non_goals`, `undecided`, and per-feed `dataset_feed`, including hash and
  scaffold regression coverage.
- A required clean-wheel acceptance job that preserves its structured evidence.
- CloudQuant Backtrader source provenance checks for runtime registration,
  test discovery, doctor diagnostics, and clean-wheel acceptance.
- `backtrader-mcp install-backtrader`, which installs the pinned CloudQuant
  source only when Backtrader is absent and otherwise reports a non-destructive
  warning for another distribution.
- LLM operation-loop surface (iteration 007): `list_jobs` (state-filtered job
  enumeration), `get_run_logs` (bounded, path-sanitized job log tails), the
  `backtrader-mcp://jobs/{job_id}/logs` resource, and a
  `list_strategy_templates` tool. `get_run_status` now reports `log_uri`,
  `elapsed_seconds`, and `eta_bound`.
- Structured client-facing error contract: tool errors cross the MCP boundary
  as `[code] message` text with optional `Suggestion:` guidance; absolute
  paths are redacted at the boundary, and unknown inputs enumerate valid
  values.
- Tool annotations (readOnlyHint/destructiveHint/idempotentHint/openWorldHint/
  title) across the 29-tool surface.

### Changed
- Ruff is the single formatter; mypy failures now block CI and pre-commit.
- The product dependency pins `cloudQuant/backtrader` at
  `3c967ed61be184c0099ba5bef55d4bed09ad0b4a`; arbitrary forks and the public
  PyPI distribution are no longer accepted as runtimes.
- Test runtime discovery supports an explicit override, sibling checkout, and
  installed-package fallback in that order, with CloudQuant provenance required
  for every candidate.
- MCP compatibility is constrained to `>=2.0.0,<2.1`, the range covered by
  the clean-room protocol verification.
- Clean-wheel acceptance now installs its own `[test]` dependency closure and
  runs the MCP v2 protocol tests from the installed target.
- `get_catalog_snapshot` defaults to the slim header; entries are opt-in via
  `include_entries`/`limit`/`offset` with pagination metadata.
  `search_strategy_catalog` reports `total`/`has_more`/`offset` and actionable
  empty-result suggestions. `preview_dataset` reports `truncation_message`
  guidance.

### Fixed
- Release metadata now has one source: Hatch derives wheel version from
  `backtrader_mcp.__version__`, and the doctor, MCP server, and product-info
  surfaces consume the same value.
- CSV adapters no longer pass `StringIO` to public Backtrader feeds that
  require a file path; generated multi-indicator templates use `RSI_Safe` for
  zero-loss windows.
- Controlled subprocess spawning and cancellation now select platform-supported
  process-group primitives, preserve the minimal Windows `SystemRoot` launch
  variable, avoid POSIX-only Popen options off POSIX, and never use signal-zero
  PID probing where it could terminate a Windows process.
- Run comparisons now detect a numeric extra metric that appears on only one
  side instead of treating the results as matched.
- Boundary-contract regression coverage for independence auditing, the local
  CLI control plane, and reports raised the enforced branch-coverage gate to
  80% and synchronized contributor and user documentation.
- A runtime root that is the active installed package is now judged by its
  distribution provenance (direct_url.json / source origin) instead of a
  `git -C` probe that could discover an unrelated enclosing repository, e.g.
  a venv nested inside the product checkout.

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
- CI workflow, coverage gating, ruff lint, mypy config,
  pre-commit hooks, `CHANGELOG.md`, `CONTRIBUTING.md`.

### Changed
- Dependency bounds were introduced for MCP and Pandas; the verified MCP range
  is subsequently narrowed under Unreleased.
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
