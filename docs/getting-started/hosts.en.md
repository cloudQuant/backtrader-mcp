# Host setup

All four host adapters start the same stdio server
(`backtrader-mcp serve`). Replace every `/ABSOLUTE/PATH` placeholder with a
real absolute path.

=== "Claude Desktop / Claude Code"

    Merge `examples/hosts/claude-desktop.json` into the host MCP
    configuration, or run:

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

    Restart Claude Desktop after editing its JSON; Claude Code verifies with
    `claude mcp list` and the interactive `/mcp` view.

=== "Codex"

    Merge `examples/hosts/codex-config.toml` into `~/.codex/config.toml`, or:

    ```bash
    codex mcp add       --env BACKTRADER_MCP_STATE_ROOT=/ABSOLUTE/PATH/.backtrader-mcp-state       --env 'BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/ABSOLUTE/PATH/data"}'       --env 'BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/ABSOLUTE/PATH/generated-strategies"}'       --env 'BACKTRADER_MCP_RUNTIMES={"default":"/ABSOLUTE/PATH/cloudquant-backtrader"}'       backtrader -- /ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp serve
    codex mcp list --json
    ```

    Codex's own `approval_policy` governs the host but does not replace this
    product's trusted local approval records.

=== "OpenCode"

    Merge `examples/hosts/opencode.json` into the global or project OpenCode
    configuration, then run `opencode mcp list` and require the `backtrader`
    server to be connected before starting a strategy request.

=== "OpenClaw"

    Edit and run `examples/hosts/openclaw-add.sh`, then keep the successful
    `openclaw mcp doctor backtrader --probe` output as setup evidence.

## First verification

A successful connection performs MCP `initialize`; the host then discovers
`tools/list`, `resources/list`, and `prompts/list`. Submit this non-mutating
first request:

```text
Use only the backtrader MCP server. Call doctor, then call
get_catalog_snapshot. Return doctor.status, the default runtime's module_file,
version and commit, plus snapshot.extensions.entry_count. Do not create a
draft, write a target, or start a run.
```

Expected evidence: `doctor.status=passed`, a `module_file` below the
registered runtime, the expected Backtrader version/commit, and catalog
`entry_count=1155`. See [First request](first-request.md) for the detailed
protocol walkthrough.
