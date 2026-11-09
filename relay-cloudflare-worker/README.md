# 可选：Cloudflare Worker 结果中转

不想在云电脑和常开机器之间跑 Tailscale 时用这个。

流程：

1. 网关 POST Webhook 唤醒 Grok Bot（和默认一样）
2. 云电脑落盘结果后，`finalize_response.py` / 快收割逻辑额外 `POST $RELAY_BASE_URL/result`
3. 网关轮询 `$RELAY_BASE_URL/response/<req_id>` 而不是 Tailscale IP

```bash
cd relay-cloudflare-worker
npx wrangler kv namespace create RESULTS
# 把返回的 id 填进 wrangler.toml
npx wrangler secret put RELAY_TOKEN
npx wrangler deploy
```

在云电脑与网关的 env 里都设置：

```env
RELAY_BASE_URL="https://<your-worker>.workers.dev"
RELAY_TOKEN="<same-secret>"
```

网关设了 `RELAY_BASE_URL` 后会优先走中转，可不再依赖 `CLOUD_BOX_HTTP`。
