# 云电脑端

部署到 Grok Bot 云电脑的 `/home/box/x-bridge/`。

关键文件：

- `bin/http_server.py`：供网关轮询 `/response/<req_id>`，并带 Round-1 快收割
- `bin/finalize_response.py`：把 `CallDynamicTool(..., write_to_file=True)` 的文件收成 JSON；若设置了 `RELAY_BASE_URL` 会顺带 POST 到 Worker
- `bin/x_call_lib.py` / `x-call.py` / `mcp_server.py`：CLI 与可选 stdio MCP（主要生产路径仍是「Webhook 例程 + 常开网关」）
- `routine/webhook-prompt.md`：创建 Webhook 例程时使用的提示词
- `supervise.sh` + `bin/ensure_tailscale.sh`：进程守护与 Tailscale 自检

环境变量见 `webhook.env.example`。
