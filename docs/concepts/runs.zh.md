# 运行、作业与扫描

## 授权链

`prepare_strategy_run` 把确切的草稿、产物、校验、数据集、运行时
（version-file 哈希 + git commit）、profile、超时、seed、analyzer 与参数网格
冻结为哈希绑定的计划，并返回签名 run token。**必须先有独立的本地审批**
（`backtrader-mcp approve --run-plan ... --yes`）才能调用
`start_strategy_run`，后者在持久作业行存在之后才消费审批与 token nonce。

## Run profile

| Profile | 模式 | 用途 |
|---|---|---|
| `runonce` | runonce | 快速单遍 |
| `runnext` | runnext | 增量遍 |
| `runonce_runnext_compare` | runonce、runnext | 确定性门禁 |
| `fixed_tests` | runonce、runnext | 默认；确定性门禁 |
| `parameter_sweep` | 每组合 runonce | typed 参数网格 |

`parameter_sweep` 在同一审批下冻结 `param_grid`（StrategySpec 参数名 → 值
列表，最多 64 个组合）。参数经 `cerebro.addstrategy(..., **override)` 传入；
结果携带 `sweep` 块，按 `return_rate` 对每个组合的指标排名。

## 作业生命周期

状态：`QUEUED`、`RUNNING`、`CANCEL_REQUESTED`、`CANCELLED`、`SUCCEEDED`、
`FAILED`、`TIMED_OUT`、`ORPHANED`。每个迁移都是 compare-and-swap 写入，仲裁
规则唯一：**终态一旦持久化永不被覆写，可见的 `CANCEL_REQUESTED` 会抑制
`SUCCEEDED`/`FAILED`/`TIMED_OUT`**。

服务器自有 watchdog（仅由 `serve` 启动）消费 worker 心跳、以宽限期强制墙钟
截止、把 worker 已死亡的作业判为孤儿，并清理脱离的候选进程组。作业报告结构
化 `error_kind`（`user_strategy`/`resource_limit`/`timeout`/`validation`/
`infrastructure`/`cancelled`/`orphaned`）。

并发上限"拒绝而非排队"：达到 `max_concurrent_jobs` 时
`start_strategy_run` 失败并附可操作建议。

## 结果与比较

成功结果恰好包含 11 项规范指标（`bar_num`、`buy_count`、`sell_count`、
`win_count`、`loss_count`、`trade_num`、`final_value`、`sharpe_ratio`、
`annual_return`、`max_drawdown`、`return_rate`）；`sharpe_ratio` 与
`annual_return` 可为空。打包的 `comparison-profile-v1` 政策是比较容差的唯一
权威，包括收紧的 `final_value` override（rel 1e-9 / abs 1e-6）。白名单
analyzer 指标出现在 `extra_metrics` 中；每次运行的 manifest 都记录运行时
commit 与解析到的 pandas/numpy 版本。
