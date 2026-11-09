#!/usr/bin/env python3
"""
Always-On Local X MCP Gateway (runs on always-on machine (Mac / Linux / Windows))
Solves Grok Bot Cloud PC sleep/hibernation completely:
1. Serves `initialize`, `ping`, `tools/list`, and `x_account_call(action='list')` 100% locally in <2ms (works even when Cloud PC is hibernating!).
2. On `tools/call` (or `POST /call`), POSTs `{id, namespace, tool, arguments}` directly to Cursor's 24/7 cloud endpoint (`https://api2.cursor.sh/automations/webhook/...`), which automatically wakes up the Grok Bot Cloud PC if sleeping.
3. Polls CLOUD_BOX_HTTP/response/<id> (or RELAY_BASE_URL when set) until raw Tweet JSON is ready.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOOLS_SPEC = json.loads((BASE_DIR / "tools_catalog.json").read_text(encoding="utf-8"))
ACCOUNT_TOOLS_CATALOG = json.loads((BASE_DIR / "account_tools_catalog.json").read_text(encoding="utf-8"))
ENV_FILE = BASE_DIR / "webhook.env"

BUILTIN_X_TOOLS = {
    "search_posts_all",
    "get_posts_counts_recent",
    "get_posts_by_id",
    "get_posts_by_ids",
    "get_posts_quoted_posts",
    "get_posts_reposted_by",
    "get_users_by_id",
    "get_users_by_username",
    "get_users_by_usernames",
    "get_users_mentions",
    "get_users_posts",
    "search_news",
    "get_trends_by_woeid",
}

def _cfg_from_env_file():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip("'").strip('"')
    return cfg

_FILE_CFG = _cfg_from_env_file()

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key) or _FILE_CFG.get(key, default)

CLOUD_BOX_HTTP = _env("CLOUD_BOX_HTTP", "http://<CLOUD_TS_IP>:18082").rstrip("/")
RELAY_BASE_URL = _env("RELAY_BASE_URL", "").rstrip("/")
RELAY_TOKEN = _env("RELAY_TOKEN", "")
DEFAULT_X_USER_ID = _env("DEFAULT_X_USER_ID", "")
DEFAULT_X_USERNAME = _env("DEFAULT_X_USERNAME", "")
DEFAULT_X_DISPLAY_NAME = _env("DEFAULT_X_DISPLAY_NAME", "")

# Wake handling for MCP tools/call (POST /call keeps the old blocking behaviour).
# Cold start of a sleeping Cloud PC can take ~3 minutes, longer than many MCP clients wait.
HEALTH_URL = os.environ.get("GROKBOT_X_HEALTH_URL") or (f"{CLOUD_BOX_HTTP}/health" if not RELAY_BASE_URL else f"{RELAY_BASE_URL}/health")
HEALTH_TIMEOUT = float(os.environ.get("GROKBOT_X_HEALTH_TIMEOUT", "2"))
INLINE_WAIT = float(os.environ.get("GROKBOT_X_INLINE_WAIT", "40"))  # seconds a cold call waits before replying "waking"
COLD_TIMEOUT = int(os.environ.get("GROKBOT_X_COLD_TIMEOUT", "360"))  # background wait for the woken Cloud PC
RESULT_TTL = int(os.environ.get("GROKBOT_X_RESULT_TTL", "600"))  # how long a finished result serves identical retries

_pending = {}
_pending_lock = threading.Lock()


def log(msg: str):
    sys.stderr.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    sys.stderr.flush()


def load_webhook_config():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip("'").strip('"')
    url = os.environ.get("GROKBOT_X_WEBHOOK_URL") or cfg.get("GROKBOT_X_WEBHOOK_URL", "")
    auth = os.environ.get("GROKBOT_X_WEBHOOK_AUTH") or cfg.get("GROKBOT_X_WEBHOOK_AUTH", "")
    return url, auth


def call_x_tool_wakeproof(tool: str, arguments: dict, namespace: str = None, timeout: int = 120) -> dict:
    if not namespace:
        namespace = "x" if tool in BUILTIN_X_TOOLS else "user-X---"

    arguments = dict(arguments or {})
    if tool in ("search_posts_all", "get_posts_by_id", "get_posts_by_ids", "get_users_posts", "get_users_mentions", "get_users_bookmarks", "get_users_timeline"):
        arguments.setdefault("post.fields", "created_at,public_metrics,author_id,lang,conversation_id")
        _pf = [x.strip() for x in str(arguments.get("post.fields", "")).split(",") if x.strip()]
        for _extra in ("article", "note_tweet"):
            if _extra not in _pf:
                _pf.append(_extra)
        arguments["post.fields"] = ",".join(_pf)
        arguments.setdefault("user.fields", "created_at,description,public_metrics,verified,location")
        arguments.setdefault("expansions", "author_id,referenced_tweets.id")

    req_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": req_id,
        "namespace": namespace,
        "tool": tool,
        "arguments": arguments,
        "created_at": time.time(),
    }

    url, auth = load_webhook_config()
    if not url:
        return {"error": "Missing GROKBOT_X_WEBHOOK_URL in webhook.env"}

    # Step 1: POST directly to Cursor's 24/7 cloud webhook (wakes up Cloud PC even if hibernating!)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.read()
            log(f"webhook {tool} id={req_id} -> {resp.status} in {time.time() - t0:.1f}s")
    except Exception as e:
        log(f"webhook {tool} id={req_id} FAILED in {time.time() - t0:.1f}s: {e!r}")
        return {"error": "webhook_trigger_failed", "message": str(e)}

    # Step 2: Poll Cloud PC /response/<req_id> (tolerates connection errors while Cloud PC wakes up)
    deadline = time.time() + timeout
    if RELAY_BASE_URL:
        poll_url = f"{RELAY_BASE_URL}/response/{req_id}"
        poll_headers = {"Authorization": f"Bearer {RELAY_TOKEN}"} if RELAY_TOKEN else {}
    else:
        poll_url = f"{CLOUD_BOX_HTTP}/response/{req_id}"
        poll_headers = {}
    while time.time() < deadline:
        try:
            req_poll = urllib.request.Request(poll_url, headers=poll_headers, method="GET")
            with urllib.request.urlopen(req_poll, timeout=4) as r:
                if r.status == 200:
                    body = json.loads(r.read().decode("utf-8"))
                    if body.get("ready"):
                        return body.get("result")
        except Exception:
            pass
        time.sleep(1.0)

    log(f"poll {tool} id={req_id} timed out after {timeout}s")
    return {"error": "timeout", "message": f"Timed out after {timeout}s waiting for response {req_id}"}


def cloud_box_awake() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=HEALTH_TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def _is_error(res) -> bool:
    return isinstance(res, dict) and "error" in res and "data" not in res


def call_x_tool_mcp(tool, arguments: dict, namespace=None) -> dict:
    """MCP entry point. Awake Cloud PC: same as before. Asleep: wake it, wait up to INLINE_WAIT,
    then reply "waking" while the request keeps running; an identical retry gets the cached result."""
    key = hashlib.sha256(
        json.dumps({"t": tool, "n": namespace, "a": arguments}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    now = time.time()
    with _pending_lock:
        for k in [k for k, e in _pending.items() if e["done"].is_set() and now - e["finished"] > RESULT_TTL]:
            del _pending[k]
        entry = _pending.get(key)
    if entry is not None:
        log(f"retry {tool}: reusing request started {now - entry['started']:.0f}s ago")
    else:
        if cloud_box_awake():
            return call_x_tool_wakeproof(tool, arguments, namespace=namespace)
        with _pending_lock:
            entry = _pending.get(key)
            start = entry is None
            if start:
                entry = {"started": time.time(), "finished": 0.0, "result": None, "done": threading.Event()}
                _pending[key] = entry
        if start:

            def run(e=entry):
                res = call_x_tool_wakeproof(tool, arguments, namespace=namespace, timeout=COLD_TIMEOUT)
                e["result"] = res
                e["finished"] = time.time()
                e["done"].set()
                log(f"cold {tool} finished in {e['finished'] - e['started']:.0f}s error={_is_error(res)}")
                if _is_error(res):
                    with _pending_lock:
                        if _pending.get(key) is e:
                            del _pending[key]

            log(f"cold {tool}: Cloud PC not reachable, waking")
            threading.Thread(target=run, daemon=True).start()

    if entry["done"].wait(INLINE_WAIT):
        return entry["result"]
    waited = time.time() - entry["started"]
    return {
        "error": "waking",
        "message": (
            f"Grok Bot 云电脑正在唤醒，已等 {waited:.0f} 秒（冷启动最长约 3 分钟）。"
            "请稍后用完全相同的参数重试：请求仍在后台执行，结果出来后会直接返回，不会重复执行。"
        ),
    }


def handle_x_account_call(arguments: dict, call=None) -> dict:
    call = call or call_x_tool_wakeproof
    action = arguments.get("action", "list")
    if action == "list":
        flt = (arguments.get("filter") or "").strip().lower()
        items = ACCOUNT_TOOLS_CATALOG
        if flt:
            items = [t for t in items if flt in t["tool"].lower() or flt in t["description"].lower()]
        return {
            "account": {"username": DEFAULT_X_USERNAME, "id": DEFAULT_X_USER_ID, "name": DEFAULT_X_DISPLAY_NAME},
            "matched_count": len(items),
            "tools": items,
            "usage_hint": "Call x_account_call with action='call', tool='<tool_name>', arguments={...}",
        }
    elif action == "call":
        target_tool = arguments.get("tool")
        if not target_tool:
            return {"error": "Missing 'tool' parameter for action='call'"}
        target_args = dict(arguments.get("arguments") or {})
        if target_tool in ("get_users_bookmarks", "get_users_bookmark_folders", "get_users_bookmarks_by_folder_id", "create_users_bookmark", "create_users_bookmark_folder", "delete_users_bookmark", "get_users_timeline"):
            if DEFAULT_X_USER_ID:
                target_args.setdefault("id", DEFAULT_X_USER_ID)
        return call(target_tool, target_args, namespace="user-X---")
    else:
        return {"error": f"Unknown action '{action}'. Use 'list' or 'call'."}


class GatewayHandler(BaseHTTPRequestHandler):
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
            self._send_json(200, {"ok": True, "service": "grokbot-x-mini-gateway", "wakeproof": True, "tools_count": len(TOOLS_SPEC)})
        elif self.path == "/tools":
            self._send_json(200, {"tools": TOOLS_SPEC})
        elif self.path.startswith("/mcp"):
            if "text/event-stream" in accept and "text/html" not in accept:
                self.send_response(405)
                self.send_header("Allow", "POST, DELETE")
                self.end_headers()
            else:
                self._send_json(200, {
                    "ok": True,
                    "service": "grokbot-x-official",
                    "mode": "always-on-wakeproof-gateway",
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

        if self.path == "/call":
            tool = data.get("tool")
            arguments = data.get("arguments") or {}
            namespace = data.get("namespace")
            timeout = int(data.get("timeout", 120))
            if not tool:
                self._send_json(400, {"error": "missing 'tool' field"})
                return
            if tool == "x_account_call":
                res = handle_x_account_call(arguments)
            else:
                res = call_x_tool_wakeproof(tool, arguments, namespace=namespace, timeout=timeout)
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
                        "serverInfo": {"name": "grokbot-x-official", "version": "1.3.0"},
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
                    res = handle_x_account_call(arguments, call=call_x_tool_mcp)
                elif name == "x_raw_call":
                    res = call_x_tool_mcp(arguments.get("tool"), arguments.get("arguments") or {}, namespace=arguments.get("namespace"))
                else:
                    res = call_x_tool_mcp(name, arguments)
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
    host = os.environ.get("GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("GATEWAY_PORT", "18082"))
    srv = ThreadingHTTPServer((host, port), GatewayHandler)
    sys.stderr.write(f"Wakeproof X MCP Gateway listening on http://{host}:{port}\n")
    srv.serve_forever()
