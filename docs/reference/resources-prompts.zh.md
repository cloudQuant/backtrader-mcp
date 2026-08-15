# 资源与 Prompt

## 资源

| URI | 名称 | MIME |
|---|---|---|
| `backtrader-mcp://product/info` | product-info | application/json |
| `backtrader-mcp://catalog/snapshot` | catalog-snapshot | application/json |
| `backtrader-mcp://strategy/templates` | strategy-templates | application/json |
| `backtrader-mcp://strategy/contract` | strategy-contract | application/json |

## 资源模板

| URI 模板 | 名称 | MIME |
|---|---|---|
| `backtrader-mcp://contracts/{schema_name}` | contract-schema | application/schema+json |
| `backtrader-mcp://datasets/{dataset_id}` | dataset-manifest | application/json |
| `backtrader-mcp://drafts/{draft_id}` | strategy-draft | application/json |
| `backtrader-mcp://jobs/{job_id}` | job-status | application/json |
| `backtrader-mcp://jobs/{job_id}/result` | job-result | application/json |
| `backtrader-mcp://jobs/{job_id}/logs` | job-logs | application/json |

读取不存在的模板实例会返回枚举允许值的结构化错误（例如
`contracts/{schema_name}` 会列出七个 schema 名）。

## Prompt

| Prompt | 参数 |
|---|---|
| `design_strategy` | goal, archetype |
| `map_dataset` | columns |
| `scaffold_strategy` | strategy_spec_json |
| `review_validation` | validation_report_json |
| `review_change` | change_set_json |
| `run_backtest` | draft_id, dataset_id |
| `review_run_result` | result_json |
| `recover_job` | job_id |

Prompt 编码了闭环工作流：设计、映射、脚手架、评审、审批感知的运行与恢复。
`run_backtest` prompt 写明 2-5 秒轮询节奏与终态集合。
