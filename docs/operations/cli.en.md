# CLI reference

The trusted local CLI (`backtrader-mcp`) is the product's control plane for
humans. Subcommands:

| Command | Purpose |
|---|---|
| `backtrader-mcp approve` | None |
| `backtrader-mcp audit-independence` | None |
| `backtrader-mcp clean` | None |
| `backtrader-mcp doctor` | None |
| `backtrader-mcp install-backtrader` | None |
| `backtrader-mcp list` | None |
| `backtrader-mcp logs` | None |
| `backtrader-mcp recover` | None |
| `backtrader-mcp serve` | None |
| `backtrader-mcp show` | None |

## Approve

The approve flow requires the signed token printed by
`prepare_strategy_changes` / `prepare_strategy_run`:

```bash
backtrader-mcp approve --change-set CHANGE_ID --change-token 'SIGNED_TOKEN' --yes
backtrader-mcp approve --run-plan RUN_PLAN_ID --run-token 'SIGNED_RUN_TOKEN' --yes
```

`--yes` is required when stdin is not a TTY; on a TTY the human types the full
subject id. Change and run approvals have different subject types and cannot
be reused for one another. Every approval audit records the approver's OS
identity.
