# First request walkthrough

The typed MCP surface is verified over the real protocol in the isolated
`mcp==2.0.0` target: `initialize`, `tools/list` (all 30 tools), `resources/
list` (4 concrete resources + 6 templates), `prompts/list` (8 prompts), and a
typed tool call.

## Example sequence (raw JSON-RPC frames)

```text
-> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
      "protocolVersion":"2025-03-26","capabilities":{},
      "clientInfo":{"name":"e2e","version":"1"}}}
<- {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{
      "name":"backtrader-mcp","version":"0.2.0",...},...}}
-> {"jsonrpc":"2.0","method":"notifications/initialized"}   (no response)
-> {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
<- {"jsonrpc":"2.0","id":2,"result":{"tools":[...30 tools...]}}
-> {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
      "name":"get_catalog_snapshot","arguments":{}}}
<- {"jsonrpc":"2.0","id":3,"result":{"isError":false,"content":[{
      "type":"text","text":"{\"schema_version\":...,\"extensions\":{
        \"entry_count\":1155,...}}"}]}}
```

## Error frames

A tool error is an `isError=true` result whose text starts with the stable
error code:

```text
Error executing tool preview_dataset: [invalid_request] preview limit must be
between 1 and 200
Suggestion: use a limit between 1 and 200
```

The server never writes anything but protocol frames to stdout; logs go to
stderr.

## Reproducing the protocol tests locally

```bash
python -m pip install -c constraints/requirements-v2.txt ".[test]"
PYTHONPATH=src python -m pytest tests/test_protocol_v2.py tests/test_stdio_transport.py -q
```

The stdio transport test spawns a real `serve` subprocess and asserts the
frames above over the production pipe.
