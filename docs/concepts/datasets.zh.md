# 数据集与 adapter

## 不可变内容寻址存储

`register_dataset` 把受限源 CSV 规范化为规范不可变 CSV（datetime 严格递增、
`_number` 归一化、UTF-8），并按内容 sha256 存入 CAS。相同源 + 相同映射参数
免重解析去重；读取期间源发生变化则注册失败。

## Typed adapter

`register_local_dataset` 接受哈希绑定的 DataSpec（1-32 个 feed、六种格式）：
`generic_csv`、`backtrader_csv`、`yahoo_csv`、`mt5_csv`、`pandas` 与
`pandas_custom_lines`。受控 worker 为每个 feed 构造具名的 Backtrader
adapter——任何格式都不会被悄悄路由到 `GenericCSVData`。

- Pandas 输入必须是物化的 `.csv` 文件（`source_type=materialized_dataframe`）；
  pickle 与调用方提供的构造器被拒绝。
- `pandas_custom_lines` 要求每条自定义 line 同时在 `lines` 与 `columns` 中
  声明。
- MT5 feed 拒绝亚分钟 timeframe（adapter 会静默截断精度）。
- `alignment.mode` 只接受 `intersection`；各 feed 必须满足 master feed 时间戳
  的 typed `minimum_overlap` 比例。

## 数据质量门禁

注册以带行号的错误拒绝非正 OHLC 价格与不一致 bar（high 低于 low、high 低于
max(open, close)、low 高于 min(open, close)）。零价/负价合法的市场可逐 feed
用 `adapter_options.allow_non_positive_prices=true` 退出；一致性始终强制。

## Bar 操作

每个 feed 可声明 `extensions.bar_operation`：

```json
{"mode": "direct"}
```

```json
{"mode": "resample", "timeframe": "minutes", "compression": 5}
```

亦支持 `replay`。resample/replay 分别经 `Cerebro.resampledata` /
`Cerebro.replaydata` 应用；成功的 fixed-test 结果记录逐 mode 的
`feed_runtime` 证据（请求格式、实际 adapter 类、bar 操作、源行数、输出 bar
数）。CloudQuant fork 默认 `bar2edge=True` 重采样——与上游 backtrader 不同。

## 派生

`derive_tabular_dataset` 以 typed 参数与精确的 source-manifest 哈希运行
`identity`、`dropna`、`returns` 或 `sma`。`returns`/`sma` 丢弃 warmup 行
（returns 为 1 行、sma 为 period-1 行），并把派生列注册为
`pandas_custom_lines` 特征线——派生数据集可直接供给 `precomputed_ml` 策略。
输出受 `max_dataset_bytes` 上限约束。
