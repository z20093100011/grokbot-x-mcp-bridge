#!/usr/bin/env python3
"""
Fast finalizer: reads a CallDynamicTool write_to_file output (/workspace/agent-tools/<uuid>.txt),
extracts the raw JSON + optional _rate_limit line, and atomically writes /home/box/x-bridge/responses/<req_id>.json.
"""
import json
import sys
from pathlib import Path

RESP_DIR = Path("/home/box/x-bridge/responses")
RESP_DIR.mkdir(parents=True, exist_ok=True)


def maybe_post_to_relay(req_id: str, result: dict) -> None:
    """Optional: when RELAY_BASE_URL is set, also push result to Cloudflare Worker."""
    import os, urllib.request
    base = os.environ.get("RELAY_BASE_URL", "").rstrip("/")
    token = os.environ.get("RELAY_TOKEN", "")
    if not base:
        return
    payload = json.dumps({"req_id": req_id, "result": result}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}/result", data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.read()
    except Exception as e:
        print(f"relay_post_failed: {e}", file=sys.stderr)



def parse_agent_tool_file(raw_text: str) -> dict:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    # Remove <cursor_untrusted_data...> wrapper lines
    clean_lines = [
        ln for ln in lines
        if not ln.startswith("<cursor_untrusted_data") and not ln.startswith("</cursor_untrusted_data")
    ]
    rate_limit = None
    json_lines = []
    for ln in clean_lines:
        if ln.startswith("X reads left for this user:"):
            rate_limit = ln
        elif ln.startswith("max_results was raised") or ln.startswith("max_results was lowered"):
            continue
        else:
            json_lines.append(ln)

    joined = "\n".join(json_lines).strip()
    obj = None
    try:
        obj = json.loads(joined)
    except Exception:
        # Try line by line if extra notes exist
        for ln in json_lines:
            if ln.startswith("{") and ln.endswith("}"):
                try:
                    obj = json.loads(ln)
                    break
                except Exception:
                    pass
    if not isinstance(obj, dict):
        obj = {"error": True, "raw": joined}
    if rate_limit:
        obj["_rate_limit"] = rate_limit
    return obj


def main():
    if len(sys.argv) < 3:
        print("Usage: finalize_response.py <req_id> <agent_tool_file>", file=sys.stderr)
        sys.exit(1)
    req_id = sys.argv[1].strip()
    src = Path(sys.argv[2].strip())
    if not src.exists():
        # Fallback check in /home/box/.cursor/projects/workspace/agent-tools/
        alt = Path("/home/box/.cursor/projects/workspace/agent-tools") / src.name
        if alt.exists():
            src = alt
    raw = src.read_text(encoding="utf-8", errors="replace")
    result = parse_agent_tool_file(raw)
    tmp_path = RESP_DIR / f".{req_id}.tmp"
    out_path = RESP_DIR / f"{req_id}.json"
    tmp_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp_path.rename(out_path)
    maybe_post_to_relay(req_id, result)
    print(f"OK: {out_path}")


if __name__ == "__main__":
    main()
