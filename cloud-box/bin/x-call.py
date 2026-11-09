#!/usr/bin/env python3
"""
Grok Bot Official X API Bridge CLI
Supports both:
- Namespace `x` (13 built-in public X read tools, 30/min & 1000/day included with subscription in Grok Bot)
- Namespace `user-X---` (83 authenticated user X tools, included with Grok Bot subscription)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from x_call_lib import call_x_tool


def main():
    parser = argparse.ArgumentParser(description="Call Grok Bot Official X Tool and get raw JSON")
    parser.add_argument("tool", help="Tool name, e.g. search_posts_all, get_users_posts, get_users_bookmarks")
    parser.add_argument("args_json", nargs="?", default="{}", help="JSON string of tool arguments")
    parser.add_argument("--namespace", choices=["x", "user-X---"], default=None, help="Force namespace")
    parser.add_argument("--timeout", type=int, default=90, help="Wait timeout in seconds")
    args = parser.parse_args()

    try:
        tool_args = json.loads(args.args_json)
    except Exception as e:
        print(json.dumps({"error": f"Invalid JSON arguments: {e}"}), file=sys.stderr)
        sys.exit(1)

    res = call_x_tool(args.tool, tool_args, namespace=args.namespace, timeout=args.timeout)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
