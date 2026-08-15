# Backtrader MCP

Backtrader MCP 是一个独立、**本地优先的 MCP 服务器**，用于构建和运行可复现的
[Backtrader](https://github.com/cloudQuant/backtrader) 策略。它把受限的 CSV
文件转换为不可变数据集，把 typed 策略意图转换为私有草稿，把经审查的草稿转换
为带超时边界的子进程运行，并持久化运行状态与报告。

产品刻意设计为**离线、仅回测**：不暴露 broker、store、凭证、实盘订单、任意
Python 执行或网络传输。

## 亮点

- **不可变数据**：内容寻址 CSV 数据集 + 数据质量门禁（OHLC 一致性）、六个
  typed adapter、resample/replay bar 操作、流式派生（`identity`/`dropna`/
  `returns`/`sma`），派生特征列可直接供给 `precomputed_ml` 策略。
- **可审查的策略意图**：七个 archetype × 两种输出 profile、不导入候选代码的
  AST 校验、白名单 analyzer（sqn/calmar/vwr/timereturn）与可选冻结 seed。
- **人工把关的授权**：HMAC 哈希绑定令牌 + 一次性 nonce、可信本地审批 CLI
  （变更与运行分开）、携带审批者 OS 身份的完整审计。
- **持久执行**：CAS 守卫的作业状态机、服务器自有 watchdog、结构化
  `error_kind` 分类、取消/超时/崩溃恢复、`parameter_sweep` 参数网格、11 项
  规范指标报告与政策驱动的比较 profile。
- **可观测可运维**：`list_jobs` / `get_run_logs` / `list_target_tree`、
  带 `Suggestion:` 建议的结构化工具错误、只读 `doctor` 诊断、针对每一类存储
  对象的保留清理。

## 快速开始

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

然后配置四个 root 变量并在 MCP 宿主中注册服务器——见
[安装](getting-started/installation.md) 与 [宿主配置](getting-started/hosts.md)。

## 相关项目

CloudQuant Backtrader 生态：

- [`cloudQuant/backtrader`](https://github.com/cloudQuant/backtrader) —— 本产品
  执行的固定 Backtrader 运行时 fork。
- [`cloudQuant/backtrader-mcp`](https://github.com/cloudQuant/backtrader-mcp) ——
  本 MCP 服务器。
- [`cloudQuant/backtrader-skills`](https://github.com/cloudQuant/backtrader-skills) ——
  Backtrader 工作流的配套 skills。
- [`cloudQuant/backtrader_web`](https://github.com/cloudQuant/backtrader_web) ——
  配套 Web 产品。
- [`cloudQuant/backtrader-agent`](https://github.com/cloudQuant/backtrader-agent) ——
  配套 Agent 产品。
- [`cloudQuant/fincore`](https://github.com/cloudQuant/fincore) —— FinCore，配套
  金融基础设施。
