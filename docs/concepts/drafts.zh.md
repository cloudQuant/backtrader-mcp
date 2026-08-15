# 草稿与校验

## 脚手架

`create_strategy_draft` 以七个 archetype 之一（`single_data_indicator`、
`multi_indicator_system`、`multi_asset_allocation`、`multi_timeframe`、
`pairs_spread`、`order_risk`、`precomputed_ml`）与两种输出 profile 之一
（`single_test`、`python_bundle`）渲染草稿。`precomputed_ml` 若首个 feed 未
声明至少一条自定义特征线会立即失败——绝不静默降级为 SMA 基线策略。生成的
模板包含 `notify_order`（受惰性 `record_fills` 开关控制）。

## 更新

`update_strategy_draft` 需要当前 revision 与精确文件哈希（乐观并发）；
`get_strategy_draft` 返回每个文件及其哈希。

## 静态校验

`validate_strategy_draft` 解析并编译 AST 而不在服务器中导入候选代码，并签发
哈希绑定的精确校验能力。直接 Strategy 类与协作式
Indicator/LineIterator/Observer/Analyzer 对象分开判定（直接 Strategy 没有
全局 `super().__init__()` 要求；自定义协作式 line 对象则有）。
`validate_strategy_spec` 对不可变数据集规范化 StrategySpec，不创建任何状态。

## StrategySpec 扩展

- `extensions.analyzers` —— `sqn`、`calmar`、`vwr`、`timereturn` 的白名单子
  集；其 typed 指标进入结果的 `extra_metrics`。
- `seed` —— 可选规范整数（0..2^32-1），冻结进 run manifest 并应用于候选
  进程的 random/numpy 状态。
