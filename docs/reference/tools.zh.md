# 工具

全部 30 个工具都带有 `readOnlyHint` / `destructiveHint` / `idempotentHint` /
`openWorldHint` 注解，宿主可以据此正确展示与门控工具。注解只是提示而非授权：
产品的真实授权是本地审批 CLI 加上哈希绑定的能力令牌（见
[安全模型](../concepts/security.zh.md)）。

工具错误以结构化 `isError` 结果跨越 MCP 边界，格式为
`[code] 消息`，可选附带 `Suggestion:` 下一步建议；错误文本中的绝对文件系统
路径会被脱敏。

| 工具 | 注解 | 描述 |
|---|---|---|
| `apply_strategy_changes` | 破坏性 · 幂等 | Apply only an exact change with a trusted local CLI approval record.          Destructive: replaces the entire managed target strategy directory after         rechecking every preimage hash. |
| `apply_strategy_repair` | 幂等 | Apply an exact-hash repair and invalidate the old validation capability. |
| `audit_independence` | 只读 · 外部世界 | Audit source imports and dynamic execution against product boundaries. |
| `cancel_strategy_run` | 破坏性 · 幂等 | Cancel a queued or running product job.          Destructive: terminates the worker and candidate processes. |
| `compare_strategy_runs` | 只读 | Compare canonical metrics and provenance using comparison-profile-v1. |
| `create_strategy_draft` | — | Create a private single-test or Python-bundle draft.          strategy_spec must satisfy the strategy-spec-v1 JSON Schema contract         (available at backtrader-mcp://contracts/strategy-spec). Each call         creates a new draft ID. |
| `derive_tabular_dataset` | 幂等 | Run one product-owned tabular transform into a new immutable dataset.          Supported profiles: identity, dropna, returns, sma. Requires the exact         source-manifest hash; identical inputs yield the same derived dataset ID. |
| `doctor` | 只读 · 外部世界 | Diagnose package dependencies, configured roots, and Backtrader runtimes. |
| `get_catalog_snapshot` | 只读 | Read the bundled immutable strategy catalog snapshot.          By default returns only counts, hashes, and provenance (extensions.         entry_count reports the 1155 records). Set include_entries=true to page         through entries with limit (1-100) and offset; pagination reports         total/has_more/truncated. Prefer search_strategy_catalog for queries. |
| `get_run_logs` | 只读 | Read bounded tails of a job's private log files.          Use after a FAILED/TIMED_OUT/ORPHANED job to diagnose the cause before         changing the strategy. tail_bytes is capped at 25000; absolute paths in         log content are redacted. |
| `get_run_result` | 只读 | Read the normalized result and Markdown report for a successful job. |
| `get_run_status` | 只读 | Read the durable state of a product-owned asynchronous run.          Includes derived polling fields: log_uri (see get_run_logs),         elapsed_seconds, and eta_bound for active jobs. Terminal states:         SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, ORPHANED. |
| `get_strategy_draft` | 只读 | Read a private draft with exact file hashes. |
| `inspect_dataset` | 只读 · 外部世界 | Inspect a confined local CSV without registering it.          Returns the detected columns and a bounded sample. Use this before         register_dataset to build an explicit column map. |
| `inspect_strategy` | 只读 | Inspect bundled or source-attached strategy metadata without importing it. |
| `list_jobs` | 只读 | List durable jobs newest-first with pagination metadata.          Filter by a job state or the pseudo-state "active" (QUEUED/RUNNING/         CANCEL_REQUESTED). Unknown states enumerate the valid values. Advance         through pages with offset while has_more is true. |
| `list_strategy_templates` | 只读 | List the fourteen archetype/output-profile scaffold templates. |
| `list_target_tree` | 只读 | Read a confined target directory tree as relative-path to sha256.          Use before prepare_strategy_changes to construct exact         expected_target_hashes preimages. |
| `prepare_strategy_changes` | 幂等 | Prepare an exact diff; this does not approve or write the target.          Returns a signed change token and the printed local approval command.         apply_strategy_changes requires the approval created by that command. |
| `prepare_strategy_run` | 幂等 | Freeze exact run inputs and return a signed plan requiring local approval.          The response includes the printed local approval command. A separate         execution approval is mandatory before start_strategy_run. For         run_profile_id=parameter_sweep, param_grid maps StrategySpec parameter         names to value lists (at most 64 combinations); one approval covers         the whole grid. |
| `preview_dataset` | 只读 | Return a bounded preview of an immutable dataset.          Includes a truncation_message telling how to raise the limit (up to the         configured max) or derive a filtered dataset. |
| `refresh_strategy_catalog` | 外部世界 | Refresh one AST root, or rebuild both metadata corpora when package_root_id is set.          Scans metadata and hashes only; corpus files are never imported or executed. |
| `register_dataset` | 幂等 · 外部世界 | Normalize a confined CSV into the immutable content-addressed store.          Requires an explicit canonical column map (datetime/open/high/low/close/         volume/openinterest). Identical content maps to the same dataset ID. |
| `register_local_dataset` | 幂等 · 外部世界 | Register one or more local feeds from a hash-bound DataSpec v1.          Accepts the six typed adapters (generic_csv, backtrader_csv, yahoo_csv,         mt5_csv, pandas, pandas_custom_lines) with optional bar_operation         (direct/resample/replay). Rejections enumerate the valid values. |
| `render_strategy_report` | 只读 | Render a successful canonical result as Markdown or JSON. |
| `search_strategy_catalog` | 只读 | Search deterministic built-in patterns by text and archetype.          Returns total/has_more/offset pagination metadata. Empty results carry         suggestions with the valid archetype list. Unknown archetypes enumerate         the valid values in the error message. |
| `start_strategy_run` | 幂等 | Consume a distinct local execution approval and launch a durable job.          Returns a job_id; poll get_run_status until a terminal state, then read         get_run_result on SUCCEEDED or get_run_logs on failure. |
| `update_strategy_draft` | — | Update one editable draft file with optimistic concurrency.          Requires the current revision and exact file hash; stale values are         rejected with a conflict error. |
| `validate_strategy_draft` | — | Statically validate a draft and issue an exact hash-bound capability.          Parses and compiles AST without importing the candidate. Every call         creates a new validation record and capability. |
| `validate_strategy_spec` | 只读 | Validate and canonicalize StrategySpec against its immutable dataset.          Read-only: no draft, token, or state record is created. |

## 工作流分组

- **数据接入**：`inspect_dataset` → `register_dataset` /
  `register_local_dataset` → `preview_dataset` → `derive_tabular_dataset`。
- **策略发现**：`get_catalog_snapshot`（默认精简 header）、
  `search_strategy_catalog`（分页）、`inspect_strategy`、
  `list_strategy_templates`、`refresh_strategy_catalog`。
- **草稿生命周期**：`create_strategy_draft` → `update_strategy_draft` →
  `validate_strategy_draft` → `apply_strategy_repair`。
- **变更授权**：`list_target_tree` → `prepare_strategy_changes` →
  （本地 CLI 审批）→ `apply_strategy_changes`。
- **运行生命周期**：`prepare_strategy_run` → （本地 CLI 审批）→
  `start_strategy_run` → `get_run_status` / `cancel_strategy_run` /
  `get_run_result` / `list_jobs` / `get_run_logs` →
  `compare_strategy_runs` / `render_strategy_report`。
