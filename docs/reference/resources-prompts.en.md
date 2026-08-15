# Resources and prompts

## Resources

| URI | Name | MIME |
|---|---|---|
| `backtrader-mcp://product/info` | product-info | application/json |
| `backtrader-mcp://catalog/snapshot` | catalog-snapshot | application/json |
| `backtrader-mcp://strategy/templates` | strategy-templates | application/json |
| `backtrader-mcp://strategy/contract` | strategy-contract | application/json |

## Resource templates

| URI template | Name | MIME |
|---|---|---|
| `backtrader-mcp://contracts/{schema_name}` | contract-schema | application/schema+json |
| `backtrader-mcp://datasets/{dataset_id}` | dataset-manifest | application/json |
| `backtrader-mcp://drafts/{draft_id}` | strategy-draft | application/json |
| `backtrader-mcp://jobs/{job_id}` | job-status | application/json |
| `backtrader-mcp://jobs/{job_id}/result` | job-result | application/json |
| `backtrader-mcp://jobs/{job_id}/logs` | job-logs | application/json |

Reading a template instance that does not exist raises a structured error
enumerating the allowed values (e.g. `contracts/{schema_name}` lists the
seven schema names).

## Prompts

| Prompt | Arguments |
|---|---|
| `design_strategy` | goal, archetype |
| `map_dataset` | columns |
| `scaffold_strategy` | strategy_spec_json |
| `review_validation` | validation_report_json |
| `review_change` | change_set_json |
| `run_backtest` | draft_id, dataset_id |
| `review_run_result` | result_json |
| `recover_job` | job_id |

Prompts encode the closed-loop workflow: design, map, scaffold, review,
approve-aware run, and recover. The `run_backtest` prompt documents the
2-5 second polling loop and the terminal states.
