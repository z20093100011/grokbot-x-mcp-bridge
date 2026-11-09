# 常开机器自启动

把 `gateway/` 目录复制到本机（建议 `~/.config/grokbot-x-gateway`），填好 `webhook.env`（可参考 `config.example.env`），再选一种自启动方式。

## macOS（LaunchAgent）

1. 复制 `com.grokbot.x-gateway.plist` 到 `~/Library/LaunchAgents/`
2. 把文件里的 `GATEWAY_DIR` 全部替换成真实目录绝对路径
3. `launchctl load -w ~/Library/LaunchAgents/com.grokbot.x-gateway.plist`

## Linux（systemd user）

```bash
mkdir -p ~/.config/systemd/user
cp grokbot-x-gateway.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now grokbot-x-gateway.service
```

## Windows

在 PowerShell 中执行 `windows-task.ps1`（先确认 `python` 在 PATH，且目录已放好）。
