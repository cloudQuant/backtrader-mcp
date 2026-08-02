#!/bin/sh
set -eu

# Replace every /ABSOLUTE/PATH placeholder before running this trusted local command.
openclaw mcp add backtrader \
  --command "/ABSOLUTE/PATH/backtrader-mcp/.runtime/bin/backtrader-mcp" \
  --arg "serve" \
  --env "BACKTRADER_MCP_STATE_ROOT=/ABSOLUTE/PATH/.backtrader-mcp-state" \
  --env 'BACKTRADER_MCP_SOURCE_ROOTS={"market_data":"/ABSOLUTE/PATH/data"}' \
  --env 'BACKTRADER_MCP_TARGET_ROOTS={"strategies":"/ABSOLUTE/PATH/generated-strategies"}' \
  --env 'BACKTRADER_MCP_RUNTIMES={"default":"/ABSOLUTE/PATH/cloudquant-backtrader"}'
# Optional tuning (defaults shown). Uncomment and adjust as needed.
# --env 'BACKTRADER_MCP_MAX_RUN_SECONDS=300'
# --env 'BACKTRADER_MCP_MAX_CONCURRENT_JOBS=4'
# --env 'BACKTRADER_MCP_LOG_LEVEL=WARNING'

openclaw mcp doctor backtrader --probe || echo "warning: openclaw doctor not supported on this version, skipping probe"
