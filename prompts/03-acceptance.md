# 联调验收清单

1. 网关本地：`curl -s http://127.0.0.1:18082/health` → `ok: true`，`tools_count` 为 14。
2. MCP：`tools/list` 含 13 个公开读工具 + `x_account_call`。
3. 公开读：`get_users_by_username`（如 `OpenAI`）返回原始 JSON，末尾可有 `_rate_limit` 或额度提示行。
4. 冷启动：先让云电脑闲置入睡，再从 MCP 调一次工具；允许先收到 `waking`，同参重试后成功。
5. 长文：对一条 X Article / 长推 `get_posts_by_id`，确认正文不在「只有标题」状态（默认会带 `article,note_tweet`）。
6. 账号侧（已连接 `user-X---` 时）：`x_account_call` → `get_users_me` / `get_users_bookmarks`。
7. 配额：公开读约每分钟 30 次、每天 1000 次（UTC 日切），勿刷爆。
