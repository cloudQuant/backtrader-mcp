# Installation

## Requirements

- Python `>=3.10,<3.14`
- The MCP Python SDK `>=2.0.0,<2.1` (validated at `2.0.0`)
- The only accepted Backtrader runtime is
  [`cloudQuant/backtrader`](https://github.com/cloudQuant/backtrader), pinned
  to commit `3c967ed61be184c0099ba5bef55d4bed09ad0b4a`.

## Install in a dedicated environment

```bash
python -m venv .runtime
. .runtime/bin/activate
python -m pip install -c constraints/requirements-v2.txt .
python -m backtrader_mcp --help
```

`constraints/requirements-v2.txt` pins the full dependency closure with
environment markers for Python 3.10-3.13. The package dependency installs the
pinned CloudQuant Backtrader source; if Backtrader is missing in another
environment, run:

```bash
backtrader-mcp install-backtrader | python -m json.tool
```

It installs only when Backtrader is absent. An existing non-CloudQuant
distribution is preserved and reported as
`installed_backtrader_untrusted`.

## Configure the roots

Register only absolute, trusted paths:

```text
BACKTRADER_MCP_STATE_ROOT=/absolute/private/state
BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/absolute/read-only/csv"}
BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/absolute/generated/strategies"}
BACKTRADER_MCP_RUNTIMES={"default":"/absolute/cloudquant-backtrader"}
```

- MCP callers receive only root IDs and relative paths; absolute or
  executable paths cannot be submitted.
- A runtime root must contain `backtrader/__init__.py` and its Git `origin`
  (or installed-package provenance) must resolve to
  `github.com/cloudquant/backtrader`. Other forks and the public PyPI package
  are rejected before a strategy run.
- If `BACKTRADER_MCP_RUNTIMES` is omitted, a verified installed CloudQuant
  distribution is registered as `default`.

## Verify with the read-only diagnostic

```bash
export BACKTRADER_MCP_STATE_ROOT='/absolute/private/state'
export BACKTRADER_MCP_SOURCE_ROOTS='{"market_data":"/absolute/read-only/csv"}'
export BACKTRADER_MCP_TARGET_ROOTS='{"strategies":"/absolute/generated/strategies"}'
export BACKTRADER_MCP_RUNTIMES='{"default":"/absolute/cloudquant-backtrader"}'
backtrader-mcp doctor | python -m json.tool
```

`doctor.status` must be `passed`. The report is stable JSON covering product
and dependency versions, installed-Backtrader provenance, root checks, and
per-runtime module file / version / commit / capabilities. The diagnostic
itself never creates the state root or writes to a source/target root.
