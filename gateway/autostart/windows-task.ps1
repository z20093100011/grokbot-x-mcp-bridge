# Run once in PowerShell (as your user) to register a logon-triggered task.
$dir = Join-Path $env:USERPROFILE ".config\grokbot-x-gateway"
$py = (Get-Command python).Source
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$dir\mini_gateway.py`"" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "GrokBot-X-Gateway" -Action $action -Trigger $trigger -Settings $settings -Description "Always-on X MCP gateway for Grok Bot bridge"
