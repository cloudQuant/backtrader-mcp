# 安装

## 环境要求

- Python `>=3.10,<3.14`
- MCP Python SDK `>=2.0.0,<2.1`（以 `2.0.0` 验证）
- 唯一可接受的 Backtrader 运行时是
  [`cloudQuant/backtrader`](https://github.com/cloudQuant/backtrader)，固定到
  commit `3c967ed61be184c0099ba5bef55d4bed09ad0b4a`。

## 在专用环境中安装

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

`constraints/requirements-v2.txt` 以带环境标记的方式固定了 Python 3.10-3.13
的完整依赖闭包。包依赖会安装固定的 CloudQuant Backtrader 源码；其他环境中若
Backtrader 缺失，可运行：

```bash
backtrader-mcp install-backtrader | python -m json.tool
```

它只在 Backtrader 缺失时安装；已存在的非 CloudQuant 发行版会被保留并以
`installed_backtrader_untrusted` 报告。

## 配置 root

只注册绝对、可信的路径：

```text
BACKTRADER_MCP_STATE_ROOT=/absolute/private/state
BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/absolute/read-only/csv"}
BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/absolute/generated/strategies"}
BACKTRADER_MCP_RUNTIMES={"default":"/absolute/cloudquant-backtrader"}
```

- MCP 调用方只能拿到 root ID 与相对路径，不能提交绝对路径或可执行路径。
- 运行时 root 必须包含 `backtrader/__init__.py`，且其 Git `origin`（或已安装
  包溯源）必须解析为 `github.com/cloudquant/backtrader`；其他 fork 与公开
  PyPI 包会在策略运行前被拒绝。
- 若省略 `BACKTRADER_MCP_RUNTIMES`，已验证的已安装 CloudQuant 分发会自动
  注册为 `default`。

## 用只读诊断验证

```bash
export BACKTRADER_MCP_STATE_ROOT='/absolute/private/state'
export BACKTRADER_MCP_SOURCE_ROOTS='{"market_data":"/absolute/read-only/csv"}'
export BACKTRADER_MCP_TARGET_ROOTS='{"strategies":"/absolute/generated/strategies"}'
export BACKTRADER_MCP_RUNTIMES='{"default":"/absolute/cloudquant-backtrader"}'
backtrader-mcp doctor | python -m json.tool
```

`doctor.status` 必须为 `passed`。报告是稳定的 JSON，覆盖产品与依赖版本、已
安装 Backtrader 溯源、root 检查，以及每个运行时的 module file / 版本 /
commit / 能力。诊断本身绝不创建 state root，也不写入 source/target root。
