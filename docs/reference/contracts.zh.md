# 契约与政策

## JSON Schema 契约

wheel 内置七个 JSON Schema 2020-12 契约（经
`backtrader-mcp://contracts/{schema_name}` 资源读取）：

- `strategy-spec` —— typed 策略意图（archetype、feeds、parameters、sizing、
  risk、run modes、allowed imports、analyzers、seed）。
- `dataset-manifest` —— 不可变数据集 manifest（内嵌 `DataSpec` 定义）。
- `corpus-manifest` —— 目录快照 header 与投影条目。
- `artifact-manifest` —— 哈希绑定的草稿产物。
- `validation-report` —— 按对象类别划分的 AST 校验发现。
- `run-manifest` —— 冻结的运行指纹（engine commit、含 pandas/numpy 的环境
  哈希、profile、seed、analyzers、审批 ID）。
- `run-result` —— 规范化指标、feed 运行时证据与扩展。

## 比较政策

`comparison-profile-v1` 是运行比较的唯一权威：六项整数指标精确相等，五项
浮点指标使用 `default_float_tolerance`（rel 1e-7、abs 1e-9），`final_value`
使用收紧的 override（rel 1e-9、abs 1e-6），可空性显式声明，非有限值比较
失败。比较代码在运行时加载该文件，测试断言两者永不漂移。

## 执行语义

- 默认 sizer：`FixedSize(stake=1)` —— `self.buy()` 成交 1 单位。
- 佣金：双边固定百分比（`percabs=True`）。
- 无 cheat-on-close：市价单在下一根 bar 开盘价成交。
- Sharpe：无风险利率 0.01、总体标准差、按 timeframe 年化（252/52/12）。
- `max_drawdown` 以正数百分比报告。
- yahoo adapter 存储未调整收盘价（`adjclose=False`）。
