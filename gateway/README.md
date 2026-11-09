# 常开机器网关

`mini_gateway.py` 在本机提供 MCP（默认 `http://127.0.0.1:18082/mcp`）。

- `tools/list` / `initialize` / 账号工具 `list`：本地返回，不依赖云电脑是否醒着
- `tools/call`：Webhook 唤醒 → 轮询 Tailscale 上的云电脑或 Cloudflare Worker
- 冷启动：可能先返回 `{"error":"waking",...}`，请用相同参数重试

复制 `config.example.env` 为 `webhook.env` 后填写。自启动见 `autostart/`。
