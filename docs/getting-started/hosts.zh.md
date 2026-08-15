# 宿主配置

四个宿主 adapter 启动的是同一个 stdio 服务器（`backtrader-mcp serve`）。请把
每个 `/ABSOLUTE/PATH` 占位符替换为真实绝对路径。

=== "Claude Desktop / Claude Code"

    把 `examples/hosts/claude-desktop.json` 合并进宿主 MCP 配置，或运行：

    ```bash
    claude mcp add-json --scope project backtrader '{
      "type": "stdio",
      "command": "/ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp",
      "args": ["serve"],
      "env": {
        "BACKTRADER_MCP_STATE_ROOT": "/ABSOLUTE/PATH/.backtrader-mcp-state",
        "BACKTRADER_MCP_SOURCE_ROOTS": "{\"market_data\":\"/ABSOLUTE/PATH/data\"}",
        "BACKTRADER_MCP_TARGET_ROOTS": "{\"strategies\":\"/ABSOLUTE/PATH/generated-strategies\"}",
        "BACKTRADER_MCP_RUNTIMES": "{\"default\":\"/ABSOLUTE/PATH/cloudquant-backtrader\"}"
      }
    }'
    claude mcp list
    ```

    编辑 Claude Desktop 的 JSON 后需重启；Claude Code 用 `claude mcp list`
    与交互式 `/mcp` 视图验证。

=== "Codex"

    把 `examples/hosts/codex-config.toml` 合并进 `~/.codex/config.toml`，或：

    ```bash
    codex mcp add       --env BACKTRADER_MCP_STATE_ROOT=/ABSOLUTE/PATH/.backtrader-mcp-state       --env 'BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/ABSOLUTE/PATH/data"}'       --env 'BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/ABSOLUTE/PATH/generated-strategies"}'       --env 'BACKTRADER_MCP_RUNTIMES={"default":"/ABSOLUTE/PATH/cloudquant-backtrader"}'       backtrader -- /ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp serve
    codex mcp list --json
    ```

    Codex 自身的 `approval_policy` 管理宿主，但不替代本产品的可信本地审批
    记录。

=== "OpenCode"

    把 `examples/hosts/opencode.json` 合并进全局或项目级 OpenCode 配置，然后
    运行 `opencode mcp list`，并要求 `backtrader` 服务器在发起策略请求前已
    连接。

=== "OpenClaw"

    编辑并运行 `examples/hosts/openclaw-add.sh`，保留成功的
    `openclaw mcp doctor backtrader --probe` 输出作为安装证据。

## 首次验证

连接成功会执行 MCP `initialize`；随后宿主发现 `tools/list`、
`resources/list` 与 `prompts/list`。提交下面这个非变更的首个请求：

```text
Use only the backtrader MCP server. Call doctor, then call
get_catalog_snapshot. Return doctor.status, the default runtime's module_file,
version and commit, plus snapshot.extensions.entry_count. Do not create a
draft, write a target, or start a run.
```

预期证据：`doctor.status=passed`、位于已注册运行时之下的 `module_file`、
预期的 Backtrader 版本 / commit，以及 catalog `entry_count=1155`。详细协议
走查见 [首个请求](first-request.md)。
