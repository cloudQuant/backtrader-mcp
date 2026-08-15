# Tools

All 30 tools carry `readOnlyHint` / `destructiveHint` / `idempotentHint` /
`openWorldHint` annotations so hosts can present and gate them correctly.
Annotations are hints, not authorization: the product's real authorization is
the local approval CLI plus hash-bound capabilities (see
[Security model](../concepts/security.en.md)).

Tool errors cross the MCP boundary as structured `isError` results in the form
`[code] message` with an optional `Suggestion:` next step; absolute filesystem
paths in error text are redacted.

| Tool | Annotations | Description |
|---|---|---|
| `apply_strategy_changes` | destructive · idempotent | Apply only an exact change with a trusted local CLI approval record.          Destructive: replaces the entire managed target strategy directory after         rechecking every preimage hash. |
| `apply_strategy_repair` | idempotent | Apply an exact-hash repair and invalidate the old validation capability. |
| `audit_independence` | readOnly · openWorld | Audit source imports and dynamic execution against product boundaries. |
| `cancel_strategy_run` | destructive · idempotent | Cancel a queued or running product job.          Destructive: terminates the worker and candidate processes. |
| `compare_strategy_runs` | readOnly | Compare canonical metrics and provenance using comparison-profile-v1. |
| `create_strategy_draft` | — | Create a private single-test or Python-bundle draft.          strategy_spec must satisfy the strategy-spec-v1 JSON Schema contract         (available at backtrader-mcp://contracts/strategy-spec). Each call         creates a new draft ID. |
| `derive_tabular_dataset` | idempotent | Run one product-owned tabular transform into a new immutable dataset.          Supported profiles: identity, dropna, returns, sma. Requires the exact         source-manifest hash; identical inputs yield the same derived dataset ID. |
| `doctor` | readOnly · openWorld | Diagnose package dependencies, configured roots, and Backtrader runtimes. |
| `get_catalog_snapshot` | readOnly | Read the bundled immutable strategy catalog snapshot.          By default returns only counts, hashes, and provenance (extensions.         entry_count reports the 1155 records). Set include_entries=true to page         through entries with limit (1-100) and offset; pagination reports         total/has_more/truncated. Prefer search_strategy_catalog for queries. |
| `get_run_logs` | readOnly | Read bounded tails of a job's private log files.          Use after a FAILED/TIMED_OUT/ORPHANED job to diagnose the cause before         changing the strategy. tail_bytes is capped at 25000; absolute paths in         log content are redacted. |
| `get_run_result` | readOnly | Read the normalized result and Markdown report for a successful job. |
| `get_run_status` | readOnly | Read the durable state of a product-owned asynchronous run.          Includes derived polling fields: log_uri (see get_run_logs),         elapsed_seconds, and eta_bound for active jobs. Terminal states:         SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, ORPHANED. |
| `get_strategy_draft` | readOnly | Read a private draft with exact file hashes. |
| `inspect_dataset` | readOnly · openWorld | Inspect a confined local CSV without registering it.          Returns the detected columns and a bounded sample. Use this before         register_dataset to build an explicit column map. |
| `inspect_strategy` | readOnly | Inspect bundled or source-attached strategy metadata without importing it. |
| `list_jobs` | readOnly | List durable jobs newest-first with pagination metadata.          Filter by a job state or the pseudo-state "active" (QUEUED/RUNNING/         CANCEL_REQUESTED). Unknown states enumerate the valid values. Advance         through pages with offset while has_more is true. |
| `list_strategy_templates` | readOnly | List the fourteen archetype/output-profile scaffold templates. |
| `list_target_tree` | readOnly | Read a confined target directory tree as relative-path to sha256.          Use before prepare_strategy_changes to construct exact         expected_target_hashes preimages. |
| `prepare_strategy_changes` | idempotent | Prepare an exact diff; this does not approve or write the target.          Returns a signed change token and the printed local approval command.         apply_strategy_changes requires the approval created by that command. |
| `prepare_strategy_run` | idempotent | Freeze exact run inputs and return a signed plan requiring local approval.          The response includes the printed local approval command. A separate         execution approval is mandatory before start_strategy_run. For         run_profile_id=parameter_sweep, param_grid maps StrategySpec parameter         names to value lists (at most 64 combinations); one approval covers         the whole grid. |
| `preview_dataset` | readOnly | Return a bounded preview of an immutable dataset.          Includes a truncation_message telling how to raise the limit (up to the         configured max) or derive a filtered dataset. |
| `refresh_strategy_catalog` | openWorld | Refresh one AST root, or rebuild both metadata corpora when package_root_id is set.          Scans metadata and hashes only; corpus files are never imported or executed. |
| `register_dataset` | idempotent · openWorld | Normalize a confined CSV into the immutable content-addressed store.          Requires an explicit canonical column map (datetime/open/high/low/close/         volume/openinterest). Identical content maps to the same dataset ID. |
| `register_local_dataset` | idempotent · openWorld | Register one or more local feeds from a hash-bound DataSpec v1.          Accepts the six typed adapters (generic_csv, backtrader_csv, yahoo_csv,         mt5_csv, pandas, pandas_custom_lines) with optional bar_operation         (direct/resample/replay). Rejections enumerate the valid values. |
| `render_strategy_report` | readOnly | Render a successful canonical result as Markdown or JSON. |
| `search_strategy_catalog` | readOnly | Search deterministic built-in patterns by text and archetype.          Returns total/has_more/offset pagination metadata. Empty results carry         suggestions with the valid archetype list. Unknown archetypes enumerate         the valid values in the error message. |
| `start_strategy_run` | idempotent | Consume a distinct local execution approval and launch a durable job.          Returns a job_id; poll get_run_status until a terminal state, then read         get_run_result on SUCCEEDED or get_run_logs on failure. |
| `update_strategy_draft` | — | Update one editable draft file with optimistic concurrency.          Requires the current revision and exact file hash; stale values are         rejected with a conflict error. |
| `validate_strategy_draft` | — | Statically validate a draft and issue an exact hash-bound capability.          Parses and compiles AST without importing the candidate. Every call         creates a new validation record and capability. |
| `validate_strategy_spec` | readOnly | Validate and canonicalize StrategySpec against its immutable dataset.          Read-only: no draft, token, or state record is created. |

## Workflow groups

- **Data intake**: `inspect_dataset` → `register_dataset` /
  `register_local_dataset` → `preview_dataset` → `derive_tabular_dataset`.
- **Strategy discovery**: `get_catalog_snapshot` (slim header by default),
  `search_strategy_catalog` (paged), `inspect_strategy`,
  `list_strategy_templates`, `refresh_strategy_catalog`.
- **Draft lifecycle**: `create_strategy_draft` → `update_strategy_draft` →
  `validate_strategy_draft` → `apply_strategy_repair`.
- **Change authorization**: `list_target_tree` → `prepare_strategy_changes`
  → (local CLI approval) → `apply_strategy_changes`.
- **Run lifecycle**: `prepare_strategy_run` → (local CLI approval) →
  `start_strategy_run` → `get_run_status` / `cancel_strategy_run` /
  `get_run_result` / `list_jobs` / `get_run_logs` →
  `compare_strategy_runs` / `render_strategy_report`.
