#!/usr/bin/env python3
"""
Cloud-box HTTP + JSON-RPC helper on BRIDGE_BIND_HOST:BRIDGE_BIND_PORT (default 0.0.0.0:18082)
Supports automatic Round-1 fast response harvesting from /workspace/agent-tools/*.txt
as soon as CallDynamicTool(..., write_to_file=True) finishes in Round 1.
Automatically registers in-flight req_id on first GET /response/<req_id> (extracting timestamp from req_id).
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from finalize_response import parse_agent_tool_file, maybe_post_to_relay
from x_call_lib import TOOLS_SPEC, call_x_tool, handle_x_account_call

RESP_DIR = Path("/home/box/x-bridge/responses")
AGENT_TOOLS_DIRS = [
    Path("/workspace/agent-tools"),
    Path("/home/box/.cursor/projects/workspace/agent-tools"),
]

LOCK = threading.Lock()
# req_id -> {"created_at": float, "baseline_files": set}
PENDING_REQS = {}
CLAIMED_FILES = set()


def current_agent_tool_files() -> set:
    res = set()
    for d in AGENT_TOOLS_DIRS:
        if d.exists():
            for p in d.glob("*.txt"):
                try:
                    res.add(str(p.resolve()))
                except Exception:
                    res.add(str(p))
    return res


CLAIMED_FILES.update(current_agent_tool_files())


def ensure_registered(req_id: str):
    with LOCK:
        if req_id in PENDING_REQS:
            return
        # Parse millisecond timestamp prefix if present: e.g. 1793092201672-2ab8c050
        created_at = time.time()
        try:
            prefix = req_id.split("-", 1)[0]
            if prefix.isdigit() and len(prefix) >= 12:
                created_at = int(prefix) / 1000.0
        except Exception:
            pass
        PENDING_REQS[req_id] = {
            "created_at": created_at,
            "registered_at": time.time(),
        }


def try_harvest_round1(req_id: str):
    resp_file = RESP_DIR / f"{req_id}.json"
    if resp_file.exists():
        with LOCK:
            PENDING_REQS.pop(req_id, None)
        return

    ensure_registered(req_id)

    with LOCK:
        now = time.time()
        # Clean up completed or expired (>45s) pending requests
        for k in list(PENDING_REQS.keys()):
            if (RESP_DIR / f"{k}.json").exists() or (now - PENDING_REQS[k]["registered_at"] > 45):
                PENDING_REQS.pop(k, None)

        if req_id not in PENDING_REQS:
            return
        # Fast-harvest in Round 1 when there is only 1 active request in flight
        if len(PENDING_REQS) != 1:
            return

        req_meta = PENDING_REQS[req_id]
        start_ts = min(req_meta["created_at"], req_meta["registered_at"]) - 1.0

        candidates = []
        for d in AGENT_TOOLS_DIRS:
            if not d.exists():
                continue
            for p in d.glob("*.txt"):
                try:
                    rp = str(p.resolve())
                except Exception:
                    rp = str(p)
                if rp in CLAIMED_FILES:
                    continue
                try:
                    st = p.stat()
                except Exception:
                    continue
                if st.st_mtime >= start_ts and st.st_size > 20:
                    candidates.append((st.st_mtime, rp, p))

        if not candidates:
            return

        candidates.sort(key=lambda x: x[0])
        for _, rp, p in candidates:
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if 'source="CallDynamicTool"' not in raw or "</cursor_untrusted_data" not in raw:
                continue
            CLAIMED_FILES.add(rp)
            parsed = parse_agent_tool_file(raw)
            RESP_DIR.mkdir(parents=True, exist_ok=True)
            tmp_file = RESP_DIR / f".{req_id}.fast.tmp"
            tmp_file.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
            tmp_file.rename(resp_file)
            try:
                maybe_post_to_relay(req_id, parsed)
            except Exception:
                pass
            PENDING_REQS.pop(req_id, None)
            sys.stderr.write(f"[fast-harvest] Matched {rp} -> {req_id}\n")
            return


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        accept = self.headers.get("Accept", "")
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "grokbot-x-bridge", "fast_harvest": True, "tools_count": len(TOOLS_SPEC)})
        elif self.path == "/tools":
            self._send_json(200, {"tools": TOOLS_SPEC})
        elif self.path.startswith("/response/"):
            req_id = self.path.split("/response/", 1)[1].strip("/")
            resp_file = RESP_DIR / f"{req_id}.json"
            if not resp_file.exists():
                try_harvest_round1(req_id)
            if resp_file.exists():
                try:
                    data = json.loads(resp_file.read_text(encoding="utf-8"))
                    with LOCK:
                        PENDING_REQS.pop(req_id, None)
                    self._send_json(200, {"ready": True, "result": data})
                except Exception as e:
                    self._send_json(200, {"ready": False, "error": str(e)})
            else:
                self._send_json(404, {"ready": False})
        elif self.path.startswith("/mcp"):
            if "text/event-stream" in accept and "text/html" not in accept:
                self.send_response(405)
                self.send_header("Allow", "POST, DELETE")
                self.end_headers()
            else:
                self._send_json(200, {
                    "ok": True,
                    "service": "grokbot-x-official",
                    "transport": "streamable-http",
                    "endpoint": "/mcp",
                    "tools_count": len(TOOLS_SPEC),
                    "tools": [t["name"] for t in TOOLS_SPEC],
                })
        else:
            self._send_json(404, {"error": "not_found"})

    def do_DELETE(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(raw)
        except Exception as e:
            self._send_json(400, {"error": f"invalid_json: {e}"})
            return

        if self.path == "/register":
            req_id = data.get("id")
            if req_id:
                with LOCK:
                    CLAIMED_FILES.update(current_agent_tool_files())
                ensure_registered(req_id)
            self._send_json(200, {"ok": True})
            return

        if self.path == "/call":
            tool = data.get("tool")
            arguments = data.get("arguments") or {}
            namespace = data.get("namespace")
            timeout = int(data.get("timeout", 90))
            if not tool:
                self._send_json(400, {"error": "missing 'tool' field"})
                return
            res = call_x_tool(tool, arguments, namespace=namespace, timeout=timeout)
            self._send_json(200, res)
            return

        if self.path.startswith("/mcp"):
            method = data.get("method")
            req_id = data.get("id")
            params = data.get("params") or {}
            if method == "initialize":
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "grokbot-x-official", "version": "1.2.0"},
                    },
                })
            elif method in ("notifications/initialized", "initialized"):
                self.send_response(202)
                self.end_headers()
            elif method == "ping":
                self._send_json(200, {"jsonrpc": "2.0", "id": req_id, "result": {}})
            elif method == "tools/list":
                self._send_json(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SPEC}})
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if name == "x_account_call":
                    res = handle_x_account_call(arguments)
                elif name == "x_raw_call":
                    res = call_x_tool(arguments.get("tool"), arguments.get("arguments") or {}, namespace=arguments.get("namespace"))
                else:
                    res = call_x_tool(name, arguments)
                is_err = isinstance(res, dict) and "error" in res and "data" not in res
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}],
                        "isError": is_err,
                    },
                })
            else:
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })
            return

        self._send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    host = os.environ.get("BRIDGE_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("BRIDGE_BIND_PORT", "18082"))
    srv = ThreadingHTTPServer((host, port), BridgeHandler)
    sys.stderr.write(f"Listening on http://{host}:{port}\n")
    srv.serve_forever()
