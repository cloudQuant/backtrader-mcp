# 发布说明

## 0.2.0（2026-08-01）

经审计加固的 P0：带六个 typed adapter 的不可变 CAS 数据、AST 校验的私有草
稿、哈希绑定的 change/run 能力与分离的本地 CLI 审批、带状态/取消/超时/恢复
的持久子进程作业、带比较政策的规范化报告，以及内置 1,155 条目录快照。

## 0.2.0 之后的加固（已合并 master，未发布）

迭代 007-013 交付：LLM 操作闭环（`list_jobs`、`get_run_logs`、
`list_target_tree`、精简目录快照、带建议的结构化 `[code]` 错误、全量工具注
解）、CAS 守卫的作业状态机与服务器自有 watchdog、流式数据管道与保留清理、
可信授权加固（审批者身份审计、一次性令牌 nonce、Windows 锁回退）、跨版本
依赖闭包 pin、扩大的测试宇宙（stdio 传输 E2E、hypothesis 性质、发布自动化）、
量化正确性（政策驱动比较、`precomputed_ml` fail-fast、白名单 analyzer、运行
时指纹、OHLC 门禁、seed）与产品能力（派生特征线、`parameter_sweep`、执行语
义文档）。

完整逐迭代细节见仓库中的 `CHANGELOG.md`。
