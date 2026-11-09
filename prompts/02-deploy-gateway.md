# 提示词 2：让本机 Claude Code / Codex 部署常开网关

在你的常开机器（家里 NAS、Mac mini、一直开着的笔记本等）上，把下面发给本机 Agent：

---

请按仓库 `gateway/` 在本机部署 Grok Bot X MCP 网关（防云电脑休眠）。

要求：
1. 安装目录建议 `~/.config/grokbot-x-gateway`。复制 `mini_gateway.py`、`tools_catalog.json`、`account_tools_catalog.json`。
2. 根据 `config.example.env` 生成 `webhook.env`（chmod 600）。填入：
   - `GROKBOT_X_WEBHOOK_URL` / `GROKBOT_X_WEBHOOK_AUTH`（来自 Grok Bot 例程）
   - Tailscale 模式：`CLOUD_BOX_HTTP=http://<CLOUD_TS_IP>:18082`
   - 或 Worker 模式：`RELAY_BASE_URL` + `RELAY_TOKEN`
   - `DEFAULT_X_USER_ID` / `DEFAULT_X_USERNAME`（可选，方便书签/时间线默认 id）
3. 若走 Tailscale：先确认本机已安装 Tailscale 客户端并登录**同一个** tailnet（与云电脑一致）。未安装时按系统安装：macOS / Windows / Linux 见 https://tailscale.com/download 。装好登录后执行 `tailscale ping <CLOUD_TS_IP>`，再 `curl -s http://<CLOUD_TS_IP>:18082/health`，两者都通过再继续；不通就先排网络，别往下配 MCP。
4. 前台试跑：`python3 mini_gateway.py`，确认 `http://127.0.0.1:18082/health` 与 `/mcp` 的 `tools/list` 本地秒回。
5. 按 `autostart/` 为本机操作系统配置自启动（macOS LaunchAgent / Linux systemd user / Windows 计划任务）。
6. 接入：
   - Claude Code：`claude mcp add --transport http grokbot-x http://127.0.0.1:18082/mcp`
   - Codex：在 `~/.codex/config.toml` 增加 `gateway/examples/codex-config.toml` 片段
7. 联调：调用 `get_users_by_username`；若云电脑在睡，应先可能返回 `error: waking`，用**完全相同参数**重试应拿到结果（冷启动可能要 1–3 分钟）。再测一条含长文的帖，确认有 `article` / `note_tweet` 字段。

不要把 webhook 密钥写进聊天记录或 git。
