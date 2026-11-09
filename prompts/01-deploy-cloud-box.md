# 提示词 1：让 Grok Bot 部署云电脑端

把下面整段发给你的 **Grok Bot**（可附上本仓库链接或把 `cloud-box/` 目录内容一并提供）：

---

请按本仓库 `cloud-box/` 在 Grok Bot 云电脑上部署「X 官方接口原始 JSON 桥接」。

要求：
1. 探测环境：`tailscale status`（若用 Tailscale）、`GetDynamicTools(namespace="x")` 与 `GetDynamicTools(namespace="user-X---")`；若已连接账号，用 `get_users_me` 得到我的 X 数字 id 与 @username，写入后续配置的占位符，不要硬编码别人的 id。
2. 创建 `/home/box/x-bridge/{bin,requests,responses,done}`，把仓库 `cloud-box/bin/*` 与 `supervise.sh` 同步进去并 `chmod +x` 可执行文件。
3. 用仓库 `cloud-box/routine/webhook-prompt.md` 创建（或更新）Webhook 例程，名称建议「X官方接口原始JSON桥接」，trigger 为 webhook。创建后告诉我界面上的 Webhook URL 与 Authorization，我确认后写入 `/home/box/x-bridge/webhook.env`（权限 600）。
4. 若走 Tailscale：先检查云电脑是否已安装 `tailscale`、是否已登录（`tailscale status`）。未安装时，提示我在 Grok Bot 里安装官方 Tailscale 插件接入同一 tailnet；或在云电脑安装 tailscale 后执行 `tailscale up`，把登录链接交给我点开完成授权。登录成功后记录 Tailscale IPv4 为 `<CLOUD_TS_IP>`；用 `ensure_tailscale.sh` + `supervise.sh` 拉起 `http_server.py`，监听 `BRIDGE_BIND_HOST/PORT`（默认 `0.0.0.0:18082`）。若走 Cloudflare Worker 中转：在 webhook.env 配置 `RELAY_BASE_URL` 与 `RELAY_TOKEN`，不必强依赖 Tailscale。
5. 验收：本机或云电脑触发一次 `get_users_by_username(username="OpenAI")`，确认 `responses/` 落盘为原始 JSON；再测 `x_account_call` 的 `get_users_me`（若已授权）。
6. 不要打印密钥全文；不要改我未授权的其他目录。

完成后用表格汇报：Tailscale IP（如有）、Webhook 是否已建、http_server 是否在跑、验收结果。
