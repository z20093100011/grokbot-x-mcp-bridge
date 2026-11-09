#!/usr/bin/env python3
"""
Stdio MCP Server for Grok Bot Official X Bridge (x + user-X---)
Exposes Grok Bot's 13 built-in public X tools (1000/day included with subscription) + key authenticated user-X--- tools
to Claude Code and Codex via JSON-RPC 2.0 over stdio.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from x_call_lib import TOOLS_SPEC, call_x_tool, handle_x_account_call


def send_response(msg: dict):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_request(req: dict):
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "grokbot-x-official", "version": "1.0.0"},
            },
        })
    elif method in ("notifications/initialized", "initialized"):
        return
    elif method == "ping":
        send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
    elif method == "tools/list":
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS_SPEC},
        })
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "x_account_call":
            res = handle_x_account_call(arguments)
        elif name == "x_raw_call":
            target_tool = arguments.get("tool")
            target_args = arguments.get("arguments") or {}
            target_ns = arguments.get("namespace")
            res = call_x_tool(target_tool, target_args, namespace=target_ns)
        else:
            res = call_x_tool(name, arguments)
        is_err = isinstance(res, dict) and "error" in res and "data" not in res
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}],
                "isError": is_err,
            },
        })
    elif req_id is not None:
        send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle_request(req)
        except Exception as e:
            sys.stderr.write(f"Error handling line: {e}\n")


if __name__ == "__main__":
    main()
