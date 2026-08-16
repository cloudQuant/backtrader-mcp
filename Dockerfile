# Backtrader MCP — local stdio MCP server
#
# The server speaks MCP over stdio. Hosts that launch containers for stdio
# servers must run with `-i` (interactive stdin) and pipe JSON-RPC frames.
#
#   docker build -t backtrader-mcp .
#   docker run -i --rm \
#     -e BACKTRADER_MCP_STATE_ROOT=/state \
#     -e BACKTRADER_MCP_SOURCE_ROOTS='{"market_data":"/data"}' \
#     -e BACKTRADER_MCP_TARGET_ROOTS='{"strategies":"/generated"}' \
#     -e BACKTRADER_MCP_RUNTIMES='{"default":"/runtime/backtrader"}' \
#     -v "$(pwd)/state:/state" -v "$(pwd)/data:/data:ro" \
#     -v "$(pwd)/generated:/generated" \
#     backtrader-mcp serve
#
# The default runtime is the pinned CloudQuant Backtrader fork installed into
# the image; mount your own checkout into BACKTRADER_MCP_RUNTIMES to override.

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV BACKTRADER_MCP_STATE_ROOT=/var/lib/backtrader-mcp/state

VOLUME ["/var/lib/backtrader-mcp/state"]

ENTRYPOINT ["backtrader-mcp"]
CMD ["serve"]
