# Backtrader MCP

**English** | [**中文**](#-中文文档)

Backtrader MCP is an independent, local-first MCP server for building and
running reproducible Backtrader strategies. It turns confined CSV files into
immutable datasets, typed strategy intent into private drafts, and reviewed
drafts into bounded subprocess runs with durable status and reports.

P0 is deliberately offline and backtest-only. It does not expose brokers,
stores, credentials, live orders, arbitrary Python execution, or network
transports.

## Distribution contract

- Python 3.10 or newer.
- MCP Python SDK `2.0.x`, using `MCPServer` and local stdio.
- Independent wheel/source distribution; Backtrader is a separately registered runtime.
- SQLite/WAL state, content-addressed CSV data, private draft files, HMAC
  capabilities, filesystem locks, idempotency records, and startup recovery.
- Product-owned `prepare_strategy_run`, `start_strategy_run`,
  `get_run_status`, `cancel_strategy_run`, and `get_run_result` tools. MCP SDK
  v2.0.0 does not provide the Tasks extension, so this product does not claim
  it.

The wheel includes seven JSON Schema contracts under
`backtrader_mcp/schemas/` and the deterministic comparison policy under
`backtrader_mcp/policies/`. It also includes its own immutable full metadata
snapshot: 1,155 unique records covering 1,152 functional tests, 1,035
three-file strategy packages, and 1,032 verified mappings. The fourteen
current-fork template entries (seven archetypes by two output profiles) remain
separate from those corpus records.

## Install without changing the base environment

From this directory, create and activate a dedicated virtual environment, then
install the package. `python` may be any supported Python 3.10+ interpreter:

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

Register only absolute, trusted roots in the host environment:

```text
BACKTRADER_MCP_STATE_ROOT=/absolute/private/state
BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/absolute/read-only/csv","functional_corpus":"/absolute/read-only/tests/functional/strategies","package_corpus":"/absolute/read-only/strategies"}
BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/absolute/generated/strategies"}
BACKTRADER_MCP_RUNTIMES={"default":"/absolute/backtrader/source/root"}
```

Root maps are JSON objects. MCP callers receive only root IDs and relative
paths; they cannot submit absolute paths or executable paths. The runtime root
must contain `backtrader/__init__.py`.

Before adding a host, export the same values in the installation shell and run
the read-only diagnostic. Quoting the JSON values prevents the shell from
interpreting them:

```bash
export BACKTRADER_MCP_STATE_ROOT='/absolute/private/state'
export BACKTRADER_MCP_SOURCE_ROOTS='{"market_data":"/absolute/read-only/csv"}'
export BACKTRADER_MCP_TARGET_ROOTS='{"strategies":"/absolute/generated/strategies"}'
export BACKTRADER_MCP_RUNTIMES='{"default":"/absolute/backtrader/source/root"}'
backtrader-mcp doctor | python -m json.tool
```

`doctor.status` must be `passed`. The report is stable JSON and includes the
installed product and dependency versions, configured root checks, supported
adapters/run profiles, and the actual Backtrader `module_file`, version, Git
commit, branch, and runtime capabilities. The CLI diagnostic itself does not
create the state root or write to a source/target root; normal MCP server
startup initializes its private state root before tools are available.

## Catalog modes

The default `snapshot` mode reads only
`backtrader_mcp/catalog_snapshot.jsonl` from this distribution. Every one of
its 1,155 records has `source_available=false`: search and provenance are
available, but `inspect_strategy` does not pretend that the original source
bytes were shipped. `list_strategy_templates` independently returns all 14
current-fork archetype/profile templates.

For an explicit source-attached rebuild, register the functional and package
corpora as two read-only IDs in `BACKTRADER_MCP_SOURCE_ROOTS`, then call:

```json
{
  "tool": "refresh_strategy_catalog",
  "arguments": {
    "source_root_id": "functional_corpus",
    "package_root_id": "package_corpus"
  }
}
```

The server scans metadata and hashes only; it never imports, executes, or
modifies a corpus file. The result reports fresh
`functional_tests`/`strategy_packages`/`mapped` counts, a content hash, and a
diagnostic if they differ from the verified 1,152/1,035/1,032 baseline.
Source-attached records use `source_available=true`; subsequent
`inspect_strategy` detects changed functional or package bytes. Supplying only
`source_root_id` preserves the smaller AST-only refresh for a registered
strategy target root.

## Host setup

Replace every `/ABSOLUTE/PATH` placeholder in the matching file.

### Claude Desktop / Claude Code

Copy `examples/hosts/claude-desktop.json` into the host's MCP configuration,
or replace every placeholder and run this complete Claude Code command:

```bash
claude mcp add-json --scope project backtrader '{
  "type": "stdio",
  "command": "/ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp",
  "args": ["serve"],
  "env": {
    "BACKTRADER_MCP_STATE_ROOT": "/ABSOLUTE/PATH/.backtrader-mcp-state",
    "BACKTRADER_MCP_SOURCE_ROOTS": "{\"market_data\":\"/ABSOLUTE/PATH/data\"}",
    "BACKTRADER_MCP_TARGET_ROOTS": "{\"strategies\":\"/ABSOLUTE/PATH/generated-strategies\"}",
    "BACKTRADER_MCP_RUNTIMES": "{\"default\":\"/ABSOLUTE/PATH/backtrader-source\"}"
  }
}'
claude mcp list
```

Restart Claude Desktop after editing its JSON. Claude Code can verify the
project-scoped server with `claude mcp list` and its interactive `/mcp` view.

### Codex

Merge `examples/hosts/codex-config.toml` into `~/.codex/config.toml` or a
trusted project's `.codex/config.toml`, then restart the Codex client. The
Codex app, Codex CLI, and Codex IDE extension share this configuration.
Codex's own `approval_policy` governs the host, but it does not replace either
of this product's trusted local approval records.

The equivalent CLI registration is:

```bash
codex mcp add \
  --env BACKTRADER_MCP_STATE_ROOT=/ABSOLUTE/PATH/.backtrader-mcp-state \
  --env 'BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/ABSOLUTE/PATH/data"}' \
  --env 'BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/ABSOLUTE/PATH/generated-strategies"}' \
  --env 'BACKTRADER_MCP_RUNTIMES={"default":"/ABSOLUTE/PATH/backtrader-source"}' \
  backtrader -- /ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp serve
codex mcp list --json
```

### OpenCode

Merge `examples/hosts/opencode.json` into the global or project OpenCode
configuration. The current configuration places each named local server
directly below `mcp`; the command is an argument vector and `enabled` is true.
Run `opencode mcp list` and require the `backtrader` server to be connected
before starting a strategy request.

### OpenClaw

Edit and run `examples/hosts/openclaw-add.sh`, then keep the successful
`openclaw mcp doctor backtrader --probe` output as setup evidence.

### First host verification

All four adapters start the same stdio server. A successful connection performs
MCP `initialize`; the host then discovers `tools/list`, `resources/list`, and
`prompts/list`. Use the host's MCP view/logs to confirm those discovery calls,
then submit this non-mutating first request:

```text
Use only the backtrader MCP server. Call doctor, then call
get_catalog_snapshot. Return doctor.status, the default runtime's module_file,
version and commit, plus snapshot.extensions.entry_count. Do not create a
draft, write a target, or start a run.
```

Expected evidence is `doctor.status=passed`, a `module_file` below the
registered runtime, the expected Backtrader version/commit, and catalog
`entry_count=1155`. Use these host-specific discovery checks:

| Host | Registration check | Interactive discovery |
| --- | --- | --- |
| Claude Code | `claude mcp list` | `/mcp` shows `backtrader`, then run the first request |
| Codex | `codex mcp list --json` | Start/restart Codex, inspect its MCP tools, then run the first request |
| OpenCode | `opencode mcp list` | Require `backtrader` connected, then run the first request |
| OpenClaw | `openclaw mcp doctor backtrader --probe` | Inspect the workspace MCP tools, then run the first request |

For raw protocol evidence independent of host UI wording, the isolated v2
protocol test performs `initialize`, `tools/list`, `resources/list`,
`prompts/list`, and a typed `get_catalog_snapshot` call.

Host configuration references:
[Claude MCP](https://code.claude.com/docs/en/mcp),
[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp),
[OpenCode MCP](https://opencode.ai/docs/mcp-servers/), and
[OpenClaw MCP](https://docs.openclaw.ai/cli/mcp).

## Upgrade and uninstall

For a compatible `0.1.x` upgrade, stop every connected host, back up the
private state root, activate the dedicated environment, and reinstall:

```bash
. .runtime/bin/activate
python -m pip install --upgrade -c constraints/requirements-v2.txt .
backtrader-mcp doctor | python -m json.tool
```

Restart the host and repeat its registration check and first request. Do not
reuse draft validation tokens, change/run tokens, or approvals across an
incompatible release. This `0.1.0` release does not migrate pre-P0 state.

To uninstall, first remove the `backtrader` MCP registration from each host
(or delete only its matching configuration entry), stop active runs, then:

```bash
. .runtime/bin/activate
python -m pip uninstall backtrader-mcp
```

Uninstalling the wheel intentionally leaves the configured state, datasets,
generated strategies, and source files untouched. Archive or remove those
paths separately only after reviewing their contents. If `.runtime` was
dedicated solely to this product, it can be removed with the platform's file
manager after deactivation.

## Closed-loop workflow

1. `inspect_dataset` reads headers and a bounded sample from a configured
   source root.
2. `register_dataset` requires an explicit canonical column map and writes a
   normalized immutable CSV to the CAS. Registration fails if the source
   changes while read.
3. `preview_dataset` reads a bounded CAS preview.
4. `derive_tabular_dataset` runs only `identity`, `dropna`, `returns`, or
   `sma` with typed parameters and an exact source-manifest hash. It creates a
   new dataset ID; no DataFrame, callable, pickle, or in-memory object crosses
   the protocol.
5. `search_strategy_catalog` selects one of seven archetypes.
6. `create_strategy_draft` renders either `single_test` or `python_bundle`.
   All seven archetypes support both profiles.
7. `update_strategy_draft` requires the current revision and file hash.
8. `validate_strategy_draft` parses and compiles AST without importing the
   candidate in the server. It classifies direct Strategy classes separately
   from cooperative Indicator/LineIterator/Observer/Analyzer objects. A direct
   Strategy does not have a global `super().__init__()` requirement; a custom
   cooperative line object does.
9. `prepare_strategy_changes` requires the validation token, exact target
   preimage hashes, and an idempotency key. It returns a signed change token
   and a complete create/replace/delete review.
10. Review the change, then run the printed command locally:

    ```bash
    backtrader-mcp approve \
      --change-set CHANGE_ID \
      --change-token 'SIGNED_TOKEN' \
      --yes
    ```

    The approval record is created in the private local database. There is no
    MCP tool for approval and no `approved=true` parameter.

11. `apply_strategy_changes` requires that approval ID, the signed change
    token, and a new idempotency key. It rechecks draft and target hashes,
    stages the complete managed directory, and uses a journaled rename
    transaction.
12. `prepare_strategy_run` requires a fresh validation token, immutable
    dataset ID, registered runtime ID, timeout, one of the fixed run profiles
    (`runonce`, `runnext`, `runonce_runnext_compare`, or `fixed_tests`), and an
    idempotency key. It freezes the exact draft, artifact, validation, dataset,
    runtime, profile, and timeout hashes and returns a signed run token.
13. Review those frozen inputs, then create a separate execution approval
    locally:

    ```bash
    backtrader-mcp approve \
      --run-plan RUN_PLAN_ID \
      --run-token 'SIGNED_RUN_TOKEN' \
      --yes
    ```

    Change approvals and run approvals have different subject types and cannot
    be reused for one another.

14. `start_strategy_run` accepts only that run plan ID, signed run token,
    execution approval ID, and a new idempotency key. Poll `get_run_status`;
    optionally call `cancel_strategy_run`; read the normalized JSON and
    Markdown report with `get_run_result`.

Job states are `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELLED`,
`SUCCEEDED`, `FAILED`, `TIMED_OUT`, and `ORPHANED`.

Successful results contain exactly eleven canonical metrics:
`bar_num`, `buy_count`, `sell_count`, `win_count`, `loss_count`, `trade_num`,
`final_value`, `sharpe_ratio`, `annual_return`, `max_drawdown`, and
`return_rate`. `sharpe_ratio` and `annual_return` are nullable. The bundled
`comparison-profile-v1` defines deterministic integer equality and floating
point tolerances for run comparison.

## Typed data adapters and bar operations

`register_local_dataset` accepts six independent typed adapters:
`generic_csv`, `backtrader_csv`, `yahoo_csv`, `mt5_csv`, `pandas`, and
`pandas_custom_lines`. Every source is parsed and normalized into an immutable
canonical CSV object before execution. The controlled worker then constructs
the named Backtrader adapter for each feed; it does not silently route every
format through `GenericCSVData`.

Pandas inputs must use `source_type=materialized_dataframe` and reference a
confined `.csv` file. Pickles, arbitrary Python objects, and caller-supplied
constructors are rejected. `pandas_custom_lines` also requires every custom
line to be declared in both `lines` and `columns`.

Each feed may declare a typed `extensions.bar_operation`:

```json
{"mode": "direct"}
```

or:

```json
{"mode": "resample", "timeframe": "minutes", "compression": 5}
```

`mode` may also be `replay`. Resample and replay are applied with
`Cerebro.resampledata` and `Cerebro.replaydata`, respectively. Successful
fixed-test results include per-mode `feed_runtime` evidence with the requested
format, actual adapter class, bar operation, source row count, and output bar
count.

## Security model

- Stdio writes protocol frames only to stdout. Candidate stdout/stderr are
  redirected to per-job private log files.
- Source, target, draft, CAS, and job paths are confined. Symlinks and parent
  traversal are rejected at caller-controlled boundaries.
- Validation and change tokens use a random 256-bit local secret, random
  nonces, expirations, and HMAC-SHA256 over canonical hash bindings.
- Apply authorization comes only from the trusted local CLI record.
- Target application replaces the entire managed strategy directory. Callers
  must provide the exact hash of every pre-existing file, including files that
  will be deleted.
- Candidate code is never imported by the MCP process. A worker launches it
  with a fixed interpreter, fixed entrypoint, minimal environment, separate
  process group, timeout, captured output, and validated result contract.

Static AST policy and a subprocess are not an OS sandbox. Reviewed candidate
code still runs with the local user's filesystem permissions. P0 is intended
for trusted local strategy development; run it in a container or restricted
OS account for hostile code. SQLite state is single-host, and the journaled
directory swap is crash-recoverable but not a multi-host distributed
transaction. Cancellation is process-based, not an MCP Tasks capability.

## Development and acceptance

Run all commands from this directory:

```bash
python -m pip install -e ".[test]"
PYTHONPATH=src python -m pytest -q
# With the four BACKTRADER_MCP_* root variables from the install section:
PYTHONPATH=src python -m backtrader_mcp doctor
PYTHONPATH=src python -m backtrader_mcp audit-independence
python scripts/run_acceptance.py --matrix all \
  --require-no-skills --require-no-agent
```

Protocol tests install `mcp==2.0.0` only into a temporary target directory.
They must not upgrade or remove the user's base-environment `mcp==1.20.0`.
The fixed acceptance entrypoint consumes a structured 14-cell artifact rather
than inferring success from pytest progress dots. It first builds a temporary
wheel, installs that wheel with `--no-deps` into a clean temporary target, and
runs pytest from a separate directory outside this source checkout. Test and
runtime dependencies must therefore already be available in the active
environment, but `backtrader_mcp` itself is imported only from the installed
wheel target.

The matrix executes all seven archetypes with both output profiles as real
runonce/runnext child-process backtests, covers all six adapters plus
resample/replay, and records inspect/register/preview, draft/validate,
prepare/apply, run, and compare evidence. Its JSON output also records the
wheel SHA-256, installed module origin,
`source_checkout_on_sys_path=false`, sibling-product absence, and the
independence audit. Callers cannot supply an arbitrary pytest target.
The wheel acceptance additionally verifies the exact full-snapshot SHA-256 and
imports/searches it from a clean temporary site directory outside this
repository, with no sibling AI product on `PYTHONPATH`.

---

# 📖 中文文档

[**English**](#backtrader-mcp) | **中文**

---

Backtrader MCP 是一个独立、本地优先的 MCP 服务器，用于构建和运行可复现的
Backtrader 策略。它把受限的 CSV 文件转换为不可变数据集，把 typed 策略意图转换为
私有草稿，把经过审查的草稿转换为带超时边界的子进程运行，并持久化运行状态与报告。

P0 版本刻意设计为离线、仅回测。它不暴露 broker、store、凭证、实盘订单、任意
Python 执行或网络传输。

## 分发契约

- Python 3.10 及以上。
- MCP Python SDK `2.0.x`，使用 `MCPServer` 与本地 stdio。
- 独立的 wheel / 源码分发；Backtrader 是单独注册的运行时。
- SQLite/WAL 状态、内容寻址的 CSV 数据、私有草稿文件、HMAC 能力令牌、文件系统
  锁、幂等性记录以及启动恢复。
- 产品自有的 `prepare_strategy_run`、`start_strategy_run`、
  `get_run_status`、`cancel_strategy_run` 和 `get_run_result` 工具。MCP SDK
  v2.0.0 不提供 Tasks 扩展，因此本产品也不声称支持。

wheel 在 `backtrader_mcp/schemas/` 下包含七个 JSON Schema 契约，在
`backtrader_mcp/policies/` 下包含确定性比较策略。它还内置自己的不可变完整元数据
快照：1,155 条唯一记录，覆盖 1,152 个功能测试、1,035 个三文件策略包和 1,032 个
已验证映射。当前 fork 的十四条模板条目（七个 archetype × 两种输出 profile）与
这些语料记录分开存放。

## 不改动基础环境的安装

在本目录下创建并激活一个专用虚拟环境，然后安装本包。`python` 可以是任意受支持的
Python 3.10+ 解释器：

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

只在宿主环境中注册绝对、可信的 root：

```text
BACKTRADER_MCP_STATE_ROOT=/absolute/private/state
BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/absolute/read-only/csv","functional_corpus":"/absolute/read-only/tests/functional/strategies","package_corpus":"/absolute/read-only/strategies"}
BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/absolute/generated/strategies"}
BACKTRADER_MCP_RUNTIMES={"default":"/absolute/backtrader/source/root"}
```

Root 映射是 JSON 对象。MCP 调用方只能拿到 root ID 和相对路径，不能提交绝对路径或
可执行路径。运行时 root 必须包含 `backtrader/__init__.py`。

新增宿主之前，先在安装 shell 中导出同样的值并运行只读诊断。给 JSON 值加引号可以
避免被 shell 解释：

```bash
export BACKTRADER_MCP_STATE_ROOT='/absolute/private/state'
export BACKTRADER_MCP_SOURCE_ROOTS='{"market_data":"/absolute/read-only/csv"}'
export BACKTRADER_MCP_TARGET_ROOTS='{"strategies":"/absolute/generated/strategies"}'
export BACKTRADER_MCP_RUNTIMES='{"default":"/absolute/backtrader/source/root"}'
backtrader-mcp doctor | python -m json.tool
```

`doctor.status` 必须为 `passed`。报告是稳定的 JSON，包含已安装产品及依赖版本、已
配置的 root 检查、支持的 adapter / run profile，以及实际的 Backtrader
`module_file`、版本、Git commit、分支和运行时能力。CLI 诊断本身不会创建 state
root，也不会写入 source / target root；正常 MCP 服务器启动时才会在工具可用之前
初始化自己的私有 state root。

## Catalog 模式

默认的 `snapshot` 模式只读取本分发中的
`backtrader_mcp/catalog_snapshot.jsonl`。它全部 1,155 条记录的
`source_available=false`：搜索和溯源可用，但 `inspect_strategy` 不会假装原始源
码字节随包分发。`list_strategy_templates` 则独立返回当前 fork 的全部 14 条
archetype / profile 模板。

若要显式重建带源码的快照，把 functional 和 package 两个语料以两个只读 ID 注册到
`BACKTRADER_MCP_SOURCE_ROOTS`，然后调用：

```json
{
  "tool": "refresh_strategy_catalog",
  "arguments": {
    "source_root_id": "functional_corpus",
    "package_root_id": "package_corpus"
  }
}
```

服务器只扫描元数据和哈希，绝不导入、执行或修改任何语料文件。结果会报告最新的
`functional_tests`/`strategy_packages`/`mapped` 计数、内容哈希，以及与已验证的
1,152/1,035/1,032 基线不一致时的诊断信息。带源码的记录使用
`source_available=true`，后续 `inspect_strategy` 可检测 functional 或 package 字节
是否变化。只提供 `source_root_id` 时，则保留针对已注册策略 target root 的更小
AST-only 刷新。

## 宿主配置

请替换对应文件中每一个 `/ABSOLUTE/PATH` 占位符。

### Claude Desktop / Claude Code

把 `examples/hosts/claude-desktop.json` 复制进宿主的 MCP 配置，或替换全部占位符后
运行下面这条完整的 Claude Code 命令：

```bash
claude mcp add-json --scope project backtrader '{
  "type": "stdio",
  "command": "/ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp",
  "args": ["serve"],
  "env": {
    "BACKTRADER_MCP_STATE_ROOT": "/ABSOLUTE/PATH/.backtrader-mcp-state",
    "BACKTRADER_MCP_SOURCE_ROOTS": "{\"market_data\":\"/ABSOLUTE/PATH/data\"}",
    "BACKTRADER_MCP_TARGET_ROOTS": "{\"strategies\":\"/ABSOLUTE/PATH/generated-strategies\"}",
    "BACKTRADER_MCP_RUNTIMES": "{\"default\":\"/ABSOLUTE/PATH/backtrader-source\"}"
  }
}'
claude mcp list
```

编辑 Claude Desktop 的 JSON 后需重启。Claude Code 可用 `claude mcp list` 及其交互
式 `/mcp` 视图验证项目级服务器。

### Codex

把 `examples/hosts/codex-config.toml` 合并到 `~/.codex/config.toml` 或可信项目的
`.codex/config.toml`，然后重启 Codex 客户端。Codex App、Codex CLI 和 Codex IDE
扩展共用这份配置。Codex 自身的 `approval_policy` 管理宿主，但不替代本产品的任一
可信本地审批记录。

等价的 CLI 注册命令：

```bash
codex mcp add \
  --env BACKTRADER_MCP_STATE_ROOT=/ABSOLUTE/PATH/.backtrader-mcp-state \
  --env 'BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/ABSOLUTE/PATH/data"}' \
  --env 'BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/ABSOLUTE/PATH/generated-strategies"}' \
  --env 'BACKTRADER_MCP_RUNTIMES={"default":"/ABSOLUTE/PATH/backtrader-source"}' \
  backtrader -- /ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp serve
codex mcp list --json
```

### OpenCode

把 `examples/hosts/opencode.json` 合并到全局或项目级 OpenCode 配置。当前配置把每个
具名的本地服务器直接放在 `mcp` 下；`command` 是参数向量，`enabled` 为 true。运行
`opencode mcp list`，并要求 `backtrader` 服务器在发起策略请求前已连接。

### OpenClaw

编辑并运行 `examples/hosts/openclaw-add.sh`，然后保留成功的
`openclaw mcp doctor backtrader --probe` 输出作为安装证据。

### 宿主首次验证

四个 adapter 启动的是同一个 stdio 服务器。连接成功会执行 MCP `initialize`，随后
宿主发现 `tools/list`、`resources/list` 和 `prompts/list`。用宿主的 MCP 视图 / 日
志确认这些发现调用，然后提交下面这个非变更的首个请求：

```text
Use only the backtrader MCP server. Call doctor, then call
get_catalog_snapshot. Return doctor.status, the default runtime's module_file,
version and commit, plus snapshot.extensions.entry_count. Do not create a
draft, write a target, or start a run.
```

预期证据是 `doctor.status=passed`、位于已注册运行时之下的 `module_file`、预期的
Backtrader 版本 / commit，以及 catalog `entry_count=1155`。各宿主的发现检查如下：

| 宿主 | 注册检查 | 交互式发现 |
| --- | --- | --- |
| Claude Code | `claude mcp list` | `/mcp` 显示 `backtrader`，然后运行首个请求 |
| Codex | `codex mcp list --json` | 启动 / 重启 Codex，查看其 MCP 工具，然后运行首个请求 |
| OpenCode | `opencode mcp list` | 要求 `backtrader` 已连接，然后运行首个请求 |
| OpenClaw | `openclaw mcp doctor backtrader --probe` | 查看工作区 MCP 工具，然后运行首个请求 |

如需独立于宿主 UI 措辞的原始协议证据，隔离的 v2 协议测试会执行 `initialize`、
`tools/list`、`resources/list`、`prompts/list` 和一次 typed
`get_catalog_snapshot` 调用。

宿主配置参考：
[Claude MCP](https://code.claude.com/docs/en/mcp)、
[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)、
[OpenCode MCP](https://opencode.ai/docs/mcp-servers/) 和
[OpenClaw MCP](https://docs.openclaw.ai/cli/mcp)。

## 升级与卸载

兼容的 `0.1.x` 升级：停止所有已连接宿主、备份私有 state root、激活专用环境并重装：

```bash
. .runtime/bin/activate
python -m pip install --upgrade -c constraints/requirements-v2.txt .
backtrader-mcp doctor | python -m json.tool
```

重启宿主并重复其注册检查和首个请求。不要跨不兼容版本复用草稿校验令牌、change/run
令牌或审批。本 `0.1.0` 版本不迁移 pre-P0 状态。

卸载时，先从每个宿主移除 `backtrader` MCP 注册（或只删除其对应配置项），停止活动
运行，然后：

```bash
. .runtime/bin/activate
python -m pip uninstall backtrader-mcp
```

卸载 wheel 时有意保留已配置的 state、数据集、生成的策略和源文件不动。请在审查内容
后再单独归档或删除这些路径。若 `.runtime` 仅专用于本产品，可在 deactivate 后用平
台文件管理器删除。

## 闭环工作流

1. `inspect_dataset` 从已配置的 source root 读取表头和有界样本。
2. `register_dataset` 需要显式的规范列映射，并把归一化的不可变 CSV 写入 CAS。读取
   期间源文件发生变化则注册失败。
3. `preview_dataset` 读取有界的 CAS 预览。
4. `derive_tabular_dataset` 只运行 `identity`、`dropna`、`returns` 或 `sma`，带
   typed 参数和精确的 source-manifest 哈希。它创建新的 dataset ID；任何
   DataFrame、callable、pickle 或内存对象都不会穿越协议。
5. `search_strategy_catalog` 在七个 archetype 中选择一个。
6. `create_strategy_draft` 渲染 `single_test` 或 `python_bundle`。七个 archetype
   都支持这两种 profile。
7. `update_strategy_draft` 需要当前 revision 和文件哈希。
8. `validate_strategy_draft` 解析并编译 AST，但不在服务器中导入候选项。它把直接
   Strategy 类与协作式 Indicator/LineIterator/Observer/Analyzer 对象分开判定。
   直接 Strategy 没有全局 `super().__init__()` 要求；自定义协作式 line 对象则需要。
9. `prepare_strategy_changes` 需要校验令牌、精确的 target 原像哈希和一个幂等键。它
   返回一个签名 change token 和完整的 create/replace/delete 审查。
10. 审查 change 后，在本地运行打印出的命令：

    ```bash
    backtrader-mcp approve \
      --change-set CHANGE_ID \
      --change-token 'SIGNED_TOKEN' \
      --yes
    ```

    审批记录写入私有本地数据库。没有用于审批的 MCP 工具，也没有 `approved=true`
    参数。

11. `apply_strategy_changes` 需要该审批 ID、签名 change token 和一个新的幂等键。它
    会重新检查草稿和 target 哈希，暂存完整的受管目录，并使用带日志的 rename 事务。
12. `prepare_strategy_run` 需要一个新的校验令牌、不可变 dataset ID、已注册的运行时
    ID、超时、固定 run profile 之一（`runonce`、`runnext`、
    `runonce_runnext_compare` 或 `fixed_tests`）以及一个幂等键。它冻结确切的草稿、
    artifact、校验、数据集、运行时、profile 和超时哈希，并返回签名 run token。
13. 审查这些冻结输入后，在本地单独创建一个执行审批：

    ```bash
    backtrader-mcp approve \
      --run-plan RUN_PLAN_ID \
      --run-token 'SIGNED_RUN_TOKEN' \
      --yes
    ```

    change 审批和 run 审批的 subject type 不同，不能互相复用。

14. `start_strategy_run` 只接受该 run plan ID、签名 run token、执行审批 ID 和一个新
    的幂等键。轮询 `get_run_status`；可选调用 `cancel_strategy_run`；用
    `get_run_result` 读取归一化的 JSON 和 Markdown 报告。

作业状态为 `QUEUED`、`RUNNING`、`CANCEL_REQUESTED`、`CANCELLED`、`SUCCEEDED`、
`FAILED`、`TIMED_OUT` 和 `ORPHANED`。

成功结果恰好包含 11 个规范指标：`bar_num`、`buy_count`、`sell_count`、
`win_count`、`loss_count`、`trade_num`、`final_value`、`sharpe_ratio`、
`annual_return`、`max_drawdown` 和 `return_rate`。`sharpe_ratio` 和
`annual_return` 可为空。内置的 `comparison-profile-v1` 定义了运行比较时确定性的整
数相等判定和浮点容差。

## Typed 数据 adapter 与 bar 操作

`register_local_dataset` 接受六个独立的 typed adapter：`generic_csv`、
`backtrader_csv`、`yahoo_csv`、`mt5_csv`、`pandas` 和 `pandas_custom_lines`。每个
源在执行前都被解析并归一化为不可变的规范 CSV 对象。受控 worker 随后为每个 feed 构
造具名的 Backtrader adapter，而不会把所有格式都悄悄走 `GenericCSVData`。

Pandas 输入必须使用 `source_type=materialized_dataframe` 并引用一个受限的 `.csv`
文件。pickle、任意 Python 对象和调用方提供的构造器都会被拒绝。`pandas_custom_lines`
还要求每条自定义 line 同时在 `lines` 和 `columns` 中声明。

每个 feed 可声明一个 typed `extensions.bar_operation`：

```json
{"mode": "direct"}
```

或：

```json
{"mode": "resample", "timeframe": "minutes", "compression": 5}
```

`mode` 也可为 `replay`。resample 和 replay 分别通过 `Cerebro.resampledata` 和
`Cerebro.replaydata` 应用。成功的 fixed-test 结果包含按 mode 记录的
`feed_runtime` 证据：请求格式、实际 adapter 类、bar 操作、源行数和输出 bar 数。

## 安全模型

- stdio 只把协议帧写入 stdout。候选项的 stdout/stderr 被重定向到按作业私有的日志
  文件。
- source、target、draft、CAS 和作业路径都被限定。符号链接和父目录穿越在调用方控制
  的边界处被拒绝。
- 校验和 change token 使用随机 256 位本地密钥、随机 nonce、过期时间，以及对规范哈
  希绑定的 HMAC-SHA256。
- apply 授权只来自可信的本地 CLI 记录。
- target 应用会替换整个受管策略目录。调用方必须提供每个既有文件的精确哈希，包括即
  将被删除的文件。
- 候选代码绝不被 MCP 进程导入。worker 用固定解释器、固定入口、最小环境、独立进程
  组、超时、捕获输出和已校验的结果契约来启动它。

静态 AST 策略加子进程并不是 OS 沙箱。经审查的候选代码仍以本地用户的文件系统权限运
行。P0 面向可信的本地策略开发；对恶意代码请在容器或受限 OS 账户中运行。SQLite 状态
是单主机的，带日志的目录交换可崩溃恢复，但不是多主机分布式事务。取消是基于进程的，
不是 MCP Tasks 能力。

## 开发与验收

所有命令在本目录下运行：

```bash
python -m pip install -e ".[test]"
PYTHONPATH=src python -m pytest -q
# 配合安装章节中的四个 BACKTRADER_MCP_* root 变量：
PYTHONPATH=src python -m backtrader_mcp doctor
PYTHONPATH=src python -m backtrader_mcp audit-independence
python scripts/run_acceptance.py --matrix all \
  --require-no-skills --require-no-agent
```

协议测试只把 `mcp==2.0.0` 安装到一个临时目标目录，绝不升级或移除用户基础环境的
`mcp==1.20.0`。固定的验收入口消费一个结构化的 14 格 artifact，而不是从 pytest 进
度点推断成功。它先构建临时 wheel，用 `--no-deps` 把该 wheel 装进干净的临时目标，
再从本源码检出之外的另一个目录运行 pytest。因此测试和运行时依赖必须已在活动环境中
可用，但 `backtrader_mcp` 本身只从已安装的 wheel 目标导入。

矩阵把全部七个 archetype × 两种输出 profile 作为真实的 runonce/runnext 子进程回测
执行，覆盖全部六个 adapter 加 resample/replay，并记录 inspect/register/preview、
draft/validate、prepare/apply、run 和 compare 证据。其 JSON 输出还记录 wheel
SHA-256、已安装模块来源、`source_checkout_on_sys_path=false`、sibling 产品缺失以及
独立性审计。调用方不能提供任意 pytest 目标。wheel 验收还会验证完整快照的确切
SHA-256，并从本仓库之外的干净临时 site 目录导入 / 搜索它，且 `PYTHONPATH` 上没有
sibling AI 产品。
