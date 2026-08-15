# 保留与清理

每一类存储对象都有保留路径：

```bash
backtrader-mcp clean --kind jobs --before 2026-01-01       # 终态作业 + 目录
backtrader-mcp clean --kind cas --before 2026-01-01        # 未引用的 CAS 对象
backtrader-mcp clean --kind drafts --before 2026-01-01     # 未引用的草稿
backtrader-mcp clean --kind approvals --before 2026-01-01  # 已消费/过期审批
backtrader-mcp clean --kind nonces --before 2026-01-01     # 已消费令牌 nonce
backtrader-mcp clean --kind audit --before 2026-01-01      # 审计历史
backtrader-mcp clean --kind idempotency --before 2026-01-01
```

- `jobs` 只删除日期之前结束的终态作业（行 + 目录），并严格校验时间戳。
- `cas` 先扫描每个 dataset manifest 收集被引用对象——被引用对象绝不删除；只
  删除早于截止时间且符合哈希文件名的文件。
- `drafts` 保留任何被 run plan 或作业引用的草稿。
- 所有清理都会写入审计记录并随后 checkpoint WAL。
- `--before` 接受 `YYYY-MM-DD` 或完整 ISO 时间戳。

`doctor` 命令在 state 数据库存在时报告只读 jobs 段（状态计数、最老活跃作业、
WAL 大小）；它绝不创建 state root。
