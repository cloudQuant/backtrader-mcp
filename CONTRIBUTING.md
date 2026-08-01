# Contributing

Thank you for contributing to Backtrader MCP. This project is a local-first,
offline, backtest-only MCP server. Keep changes inside the product boundaries
documented in `IMPLEMENTATION_SPEC.md` and `README.md`.

## Development setup

All commands run from the repository root.

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt ".[test]"
```

The test suite runs real Backtrader backtests in a subprocess. It expects a
registered runtime root that contains `backtrader/__init__.py`. The shared
test fixture in `tests/conftest.py` uses the repository parent directory as the
default runtime root, so a sibling `backtrader` source checkout satisfies it.

## Running checks

```bash
PYTHONPATH=src python -m pytest -q                       # tests + coverage (fails under 80%)
ruff check src tests scripts                              # lint
ruff format --check src tests scripts                     # format check
PYTHONPATH=src python -m mypy src/backtrader_mcp          # types (advisory)
PYTHONPATH=src python -m backtrader_mcp audit-independence
```

Acceptance (builds a wheel and runs the structured matrix from outside the
checkout):

```bash
python scripts/run_acceptance.py --matrix all --require-no-skills --require-no-agent
```

## Tuning environment variables

All optional with sensible defaults. JSON-based host configs cannot contain
comments, so set these in the host `env` block (or the install shell) when a
default is too small or large for your workload.

| Variable | Default | Purpose |
|---|---|---|
| `BACKTRADER_MCP_MAX_DATASET_BYTES` | 67108864 | Max CSV size accepted by `register_dataset` |
| `BACKTRADER_MCP_MAX_PREVIEW_ROWS` | 200 | Rows returned by `preview_dataset` |
| `BACKTRADER_MCP_MAX_RUN_SECONDS` | 300 | Wall-clock cap per run |
| `BACKTRADER_MCP_MAX_RUN_CPU_SECONDS` | 0 (auto) | CPU-second cap; `0` derives `MAX_RUN_SECONDS + 30` |
| `BACKTRADER_MCP_MAX_RUN_MEMORY_BYTES` | 2147483648 | Candidate subprocess address-space cap |
| `BACKTRADER_MCP_MAX_RUN_FILE_SIZE_BYTES` | 268435456 | Candidate subprocess file-size cap |
| `BACKTRADER_MCP_MAX_RUN_PROCESSES` | 8 | Candidate process-count cap (fork-bomb guard) |
| `BACKTRADER_MCP_MAX_CONCURRENT_JOBS` | 4 | Max simultaneously active jobs |
| `BACKTRADER_MCP_LOG_LEVEL` | WARNING | Product logger level (logs go to stderr) |

For hosts with a tool timeout (e.g. Codex `tool_timeout_sec`), keep it at or
above `BACKTRADER_MCP_MAX_RUN_SECONDS` plus a buffer.

## Product boundaries

- Never import sibling Skills or Agent products. `audit-independence` enforces
  this; keep it green.
- Candidate strategy code is never imported by the MCP server process. It runs
  in a controlled subprocess with a fixed interpreter, minimal environment,
  timeout, captured output, and resource limits. Static AST validation is a
  policy layer, not an OS sandbox.
- Validation, change, and run tokens bind to exact hashes. Applying changes and
  starting runs require distinct approvals created only by the trusted local
  CLI. Never add an MCP tool that grants approval.
- Reproducibility contracts (`strategy-spec-v1`, `run-result-v1`) are versioned.
  Extend them backward-compatibly via optional fields and `extensions` unless
  bumping a major version with a migration path.

## Adding a strategy archetype

1. Add the archetype name to `ARCHETYPES` in `src/backtrader_mcp/contracts.py`
   and the `archetype` enum in
   `src/backtrader_mcp/schemas/strategy-spec.schema.json`.
2. Add a deterministic strategy body in `src/backtrader_mcp/scaffold.py`.
3. Update `src/backtrader_mcp/catalog.py` archetype indexing if applicable.
4. Add positive and negative tests under `tests/`.

## Commit and PR style

Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
`chore:`, `perf:`, `ci:`). Open PRs against `master` and include a test plan.
