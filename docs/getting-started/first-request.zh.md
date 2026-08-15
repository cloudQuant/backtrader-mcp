# 首个请求走查

typed MCP 表面在隔离的 `mcp==2.0.0` target 上经真实协议验证：`initialize`、
`tools/list`（全部 30 个工具）、`resources/list`（4 个具体资源 + 6 个模板）、
`prompts/list`（8 个 prompt）与一次 typed 工具调用。

## 示例序列（原始 JSON-RPC 帧）

```text
-> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
      "protocolVersion":"2025-03-26","capabilities":{},
      "clientInfo":{"name":"e2e","version":"1"}}}
<- {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{
      "name":"backtrader-mcp","version":"0.2.0",...},...}}
-> {"jsonrpc":"2.0","method":"notifications/initialized"}   （无响应）
-> {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
<- {"jsonrpc":"2.0","id":2,"result":{"tools":[...30 个工具...]}}
-> {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
      "name":"get_catalog_snapshot","arguments":{}}}
<- {"jsonrpc":"2.0","id":3,"result":{"isError":false,"content":[{
      "type":"text","text":"{\"schema_version\":...,\"extensions\":{
        \"entry_count\":1155,...}}"}]}}
```

## 错误帧

工具错误是 `isError=true` 的结果，文本以稳定错误码开头：

```text
Error executing tool preview_dataset: [invalid_request] preview limit must be
between 1 and 200
Suggestion: use a limit between 1 and 200
```

服务器 stdout 只写协议帧；日志走 stderr。

## 本地复现协议测试

```bash
python -m pip install -c constraints/requirements-v2.txt ".[test]"
PYTHONPATH=src python -m pytest tests/test_protocol_v2.py tests/test_stdio_transport.py -q
```

stdio 传输测试会拉起真实的 `serve` 子进程，并在生产管道上断言上述帧。
