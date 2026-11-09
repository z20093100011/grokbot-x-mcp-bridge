import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

BRIDGE_DIR = Path("/home/box/x-bridge")
REQ_DIR = BRIDGE_DIR / "requests"
RESP_DIR = BRIDGE_DIR / "responses"
DONE_DIR = BRIDGE_DIR / "done"
ENV_FILE = BRIDGE_DIR / "webhook.env"

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

TOOLS_SPEC = json.loads((Path(__file__).parent / "tools_catalog.json").read_text(encoding="utf-8"))
_OLD_TOOLS_SPEC = [
    {
        "name": "search_posts_all",
        "description": "[Built-in X] Full-archive X post search (1000/day, 30/min included with subscription). Query operators: from:handle, min_likes:N, min_reposts:N, -is:retweet, -is:reply, lang:zh, since:YYYY-MM-DD.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "max_results": {"type": "integer", "description": "Max results per page (up to 25)"},
                "sort_order": {"type": "string", "enum": ["recency", "relevancy"]},
                "start_time": {"type": "string", "description": "ISO 8601 UTC start time"},
                "end_time": {"type": "string", "description": "ISO 8601 UTC end time"},
                "pagination_token": {"type": "string"},
                "post.fields": {"type": "string", "default": "created_at,public_metrics,author_id,lang,conversation_id,entities,referenced_tweets"},
                "user.fields": {"type": "string", "default": "created_at,description,public_metrics,verified,location,username,name"},
                "expansions": {"type": "string", "default": "author_id,referenced_tweets.id"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_posts_counts_recent",
        "description": "[Built-in X] Count recent posts (last 7 days) matching a query by minute, hour, or day.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "granularity": {"type": "string", "enum": ["minute", "hour", "day"]},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_posts_by_id",
        "description": "[Built-in X] Get a single post by ID with full metrics and author expansion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "post.fields": {"type": "string"},
                "user.fields": {"type": "string"},
                "expansions": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "get_posts_by_ids",
        "description": "[Built-in X] Get multiple posts by comma-separated IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "string", "description": "Comma-separated post IDs"},
                "post.fields": {"type": "string"},
                "user.fields": {"type": "string"},
                "expansions": {"type": "string"}
            },
            "required": ["ids"]
        }
    },
    {
        "name": "get_users_by_username",
        "description": "[Built-in X] Get user profile and public_metrics by @username (without @).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "user.fields": {"type": "string", "default": "id,name,username,description,public_metrics,created_at,verified,location"}
            },
            "required": ["username"]
        }
    },
    {
        "name": "get_users_posts",
        "description": "[Built-in X] Get posts authored by a numeric user ID (resolve username with get_users_by_username first).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Numeric user ID"},
                "max_results": {"type": "integer"},
                "exclude": {"type": "string", "description": "e.g. retweets,replies"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "pagination_token": {"type": "string"},
                "post.fields": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "search_news",
        "description": "[Built-in X] Search X curated news stories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_age_hours": {"type": "integer"},
                "max_results": {"type": "integer"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_trends_by_woeid",
        "description": "[Built-in X] Get X trending topics by WOEID (1 = worldwide).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "woeid": {"type": "integer"},
                "max_trends": {"type": "integer"}
            },
            "required": ["woeid"]
        }
    },
    {
        "name": "search_users",
        "description": "[Account user-X---] Search X user accounts by keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "user.fields": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_users_bookmarks",
        "description": "[Account user-X---] Get authenticated user's bookmarks (default id='<YOUR_X_USER_ID>').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "default": "<YOUR_X_USER_ID>"},
                "max_results": {"type": "integer"},
                "pagination_token": {"type": "string"},
                "post.fields": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "get_users_timeline",
        "description": "[Account user-X---] Get authenticated user's home timeline (default id='<YOUR_X_USER_ID>').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "default": "<YOUR_X_USER_ID>"},
                "max_results": {"type": "integer"},
                "pagination_token": {"type": "string"},
                "post.fields": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "x_raw_call",
        "description": "Generic dispatcher for ANY of the 13 `x` tools or 96 `user-X---` tools by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Exact tool name in `x` or `user-X---`"},
                "arguments": {"type": "object", "description": "Tool arguments object"},
                "namespace": {"type": "string", "enum": ["x", "user-X---"]}
            },
            "required": ["tool", "arguments"]
        }
    }
]


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
    key = os.environ.get("GROKBOT_X_WEBHOOK_KEY") or cfg.get("GROKBOT_X_WEBHOOK_KEY", "")
    if not auth and key:
        auth = f"Bearer {key}" if not key.lower().startswith("bearer ") else key
    return url, auth


def trigger_webhook(payload: dict):
    url, auth = load_webhook_config()
    if not url:
        return False, "Missing GROKBOT_X_WEBHOOK_URL in /home/box/x-bridge/webhook.env"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


def call_x_tool(tool: str, arguments: dict, namespace: str = None, timeout: int = 90) -> dict:
    REQ_DIR.mkdir(parents=True, exist_ok=True)
    RESP_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    if not namespace:
        namespace = "x" if tool in BUILTIN_X_TOOLS else "user-X---"

    # Default fields for rich raw JSON if not specified
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
    req_payload = {
        "id": req_id,
        "namespace": namespace,
        "tool": tool,
        "arguments": arguments,
        "created_at": time.time(),
    }

    req_file = REQ_DIR / f"{req_id}.json"
    tmp_file = REQ_DIR / f".{req_id}.tmp"
    resp_file = RESP_DIR / f"{req_id}.json"

    tmp_file.write_text(json.dumps(req_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.rename(req_file)

    ok, msg = trigger_webhook(req_payload)
    if not ok:
        return {
            "error": "webhook_not_configured_or_failed",
            "message": msg,
            "request_file": str(req_file),
            "hint": "Set GROKBOT_X_WEBHOOK_URL and GROKBOT_X_WEBHOOK_AUTH in /home/box/x-bridge/webhook.env",
        }

    deadline = time.time() + timeout
    while time.time() < deadline:
        if resp_file.exists():
            try:
                content = resp_file.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception:
                time.sleep(0.2)
        time.sleep(0.5)

    return {
        "error": "timeout",
        "message": f"Timed out after {timeout}s waiting for {resp_file}",
        "request_id": req_id,
    }


ACCOUNT_TOOLS_CATALOG = json.loads((Path(__file__).parent / "account_tools_catalog.json").read_text(encoding="utf-8"))

def handle_x_account_call(arguments: dict) -> dict:
    action = arguments.get("action", "list")
    if action == "list":
        flt = (arguments.get("filter") or "").strip().lower()
        items = ACCOUNT_TOOLS_CATALOG
        if flt:
            items = [t for t in items if flt in t["tool"].lower() or flt in t["description"].lower()]
        return {
            "account": {"username": os.environ.get("DEFAULT_X_USERNAME", ""), "id": os.environ.get("DEFAULT_X_USER_ID", ""), "name": os.environ.get("DEFAULT_X_DISPLAY_NAME", "")},
            "matched_count": len(items),
            "tools": items,
            "usage_hint": "Call x_account_call with action='call', tool='<tool_name>', arguments={...}"
        }
    elif action == "call":
        target_tool = arguments.get("tool")
        if not target_tool:
            return {"error": "Missing 'tool' parameter for action='call'"}
        target_args = dict(arguments.get("arguments") or {})
        if target_tool in ("get_users_bookmarks", "get_users_bookmark_folders", "get_users_bookmarks_by_folder_id", "create_users_bookmark", "create_users_bookmark_folder", "delete_users_bookmark", "get_users_timeline"):
            uid = os.environ.get("DEFAULT_X_USER_ID", "")
            if uid:
                target_args.setdefault("id", uid)
        return call_x_tool(target_tool, target_args, namespace="user-X---")
    else:
        return {"error": f"Unknown action '{action}'. Use 'list' or 'call'."}


def normalize_x_arguments(tool: str, arguments: dict) -> dict:
    args = dict(arguments or {})
    # Map underscore aliases to dot field names
    alias_map = {
        "user_fields": "user.fields",
        "tweet_fields": "post.fields",
        "post_fields": "post.fields",
        "media_fields": "media.fields",
        "place_fields": "place.fields",
        "poll_fields": "poll.fields",
    }
    for k_old, k_new in alias_map.items():
        if k_old in args:
            val = args.pop(k_old)
            if k_new not in args:
                args[k_new] = val

    # Convert list values to comma-separated strings where X expects strings
    csv_keys = {
        "user.fields", "post.fields", "media.fields", "place.fields", "poll.fields",
        "expansions", "exclude", "ids", "usernames"
    }
    for k in list(args.keys()):
        if k in csv_keys and isinstance(args[k], (list, tuple)):
            args[k] = ",".join(str(x) for x in args[k])

    if "username" in args and isinstance(args["username"], str):
        args["username"] = args["username"].lstrip("@")

    return args
