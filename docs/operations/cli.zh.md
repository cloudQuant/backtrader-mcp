# CLI 参考

可信本地 CLI（`backtrader-mcp`）是面向人类的控制面。子命令：

| 命令 | 用途 |
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

## 审批

审批流程需要 `prepare_strategy_changes` / `prepare_strategy_run` 打印的签名
令牌：

```bash
backtrader-mcp approve --change-set CHANGE_ID --change-token 'SIGNED_TOKEN' --yes
backtrader-mcp approve --run-plan RUN_PLAN_ID --run-token 'SIGNED_RUN_TOKEN' --yes
```

stdin 非 TTY 时必须带 `--yes`；TTY 下由人类输入完整 subject id。change 与
run 审批的 subject type 不同，不能互相复用。每条审批审计都记录审批者的 OS
身份。
