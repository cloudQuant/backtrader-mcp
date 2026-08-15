from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.acceptance


def _send(process: subprocess.Popen, message: dict, timeout: float = 10.0) -> dict:
    """Send one newline-delimited JSON-RPC frame and read the response."""
    import select

    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    assert ready, f"no response within {timeout}s for {message['method']}"
    line = process.stdout.readline()
    assert line, "server closed stdout without a response"
    return json.loads(line)


def test_stdio_serve_transport_end_to_end(tmp_path):
    """The production transport: a subprocess `serve` over raw stdio frames."""
    env = dict(os.environ)
    env["BACKTRADER_MCP_STATE_ROOT"] = str(tmp_path / "state")
    env["BACKTRADER_MCP_SOURCE_ROOTS"] = "{}"
    env["BACKTRADER_MCP_TARGET_ROOTS"] = "{}"
    env["BACKTRADER_MCP_RUNTIMES"] = "{}"
    # Python block-buffers stdout on pipes; without unbuffered mode the
    # protocol frames sit in the child's buffer instead of crossing the pipe.
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "backtrader_mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        init = _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-e2e", "version": "1.0"},
                },
            },
        )
        assert init.get("result", {}).get("serverInfo", {}).get("name") == "backtrader-mcp"
        # A notification: the server must NOT respond to it.
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        process.stdin.flush()
        tools = _send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert {"doctor", "get_catalog_snapshot", "list_jobs"} <= names
        doctor = _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "doctor", "arguments": {}},
            },
        )
        assert doctor["result"]["isError"] is False
        content = json.loads(doctor["result"]["content"][0]["text"])
        assert content["schema_version"] == "backtrader-mcp-doctor-v1"
        assert "runtimes" in content
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert process.returncode is not None
