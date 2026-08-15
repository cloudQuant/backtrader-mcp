# Release notes

## 0.2.0 (2026-08-01)

The audited, hardened P0: immutable CAS data with six typed adapters, private
drafts with AST validation, hash-bound change/run capabilities with distinct
local CLI approvals, durable subprocess jobs with status/cancel/timeout/
recovery, normalized reports with a comparison policy, and a bundled
1,155-record catalog snapshot.

## Post-0.2.0 hardening (merged to master, unreleased)

Iterations 007-013 delivered: the LLM operation loop (`list_jobs`,
`get_run_logs`, `list_target_tree`, slim catalog snapshot, structured
`[code]` errors with suggestions, full tool annotations), the CAS-guarded job
state machine with a server-owned watchdog, a streamed data pipeline with
source-level dedup and retention cleanup, trusted-authorization hardening
(approver identity audits, one-time token nonces, Windows lock fallback), a
pinned cross-version dependency closure, the expanded test universe (stdio
transport E2E, hypothesis properties, release automation), quant correctness
(policy-driven comparison, `precomputed_ml` fail-fast, allowlisted analyzers,
runtime fingerprints, OHLC gating, seeds), and product capabilities
(derived feature lines, `parameter_sweep`, execution-semantics documentation).

See `CHANGELOG.md` in the repository for the complete per-iteration detail.
