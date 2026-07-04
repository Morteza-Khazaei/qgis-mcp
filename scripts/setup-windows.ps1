<#
.SYNOPSIS
    Windows-side setup for QGIS MCP <-> WSL2 connectivity.

.DESCRIPTION
    Run this ONCE on Windows (in PowerShell), and re-run any time you want to verify
    or repair the setup, or if the QGIS MCP plugin fails to start with
    "WinError 10013: An attempt was made to access a socket in a way forbidden by
    its access permissions". It is idempotent - safe to run multiple times.

    What it does:
      1. Removes any stale SINGLE-PORT portproxy rule on port 9876. An earlier
         version of this script forwarded 0.0.0.0:9876 -> 127.0.0.1:9876, i.e. the
         SAME port the plugin itself binds to. That only worked as long as the
         plugin's socket was already open first. The moment QGIS restarts and the
         plugin tries to rebind 127.0.0.1:9876, Windows sees the port already
         exclusively claimed by the portproxy rule and refuses the bind with
         WinError 10013 - the plugin then fails to start. Deleting that rule is
         required before the plugin can bind again.
      2. Creates a DUAL-PORT portproxy rule instead: 0.0.0.0:19876 -> 127.0.0.1:9876.
         The external port (19876, what WSL connects to) is now different from the
         plugin's own internal port (9876, fixed in the QGIS MCP plugin panel), so
         they never compete for the same bind. This is required because the QGIS
         MCP plugin only binds to 127.0.0.1 (localhost) and has no option to listen
         on all interfaces - without some proxy, WSL cannot reach the plugin's
         socket even with the firewall open.
      3. Adds a Windows Firewall rule allowing inbound TCP 19876 (and removes the
         old rule for 9876, which is no longer needed since nothing external
         connects to 9876 directly anymore).

    It does NOT need to know WSL's IP address: the portproxy listens on 0.0.0.0,
    i.e. all interfaces, including the virtual adapter WSL connects through.
    Only the WSL SIDE needs to know Windows' IP (as seen from WSL) and the external
    proxy port, and that is handled by setup-wsl.sh, which re-detects the IP every
    time it's run (that IP is what changes across WSL restarts, not this side).

.NOTES
    Must be run as Administrator. Re-run any time the QGIS MCP plugin fails to
    start with WinError 10013, or after every Windows reboot if the portproxy rule
    doesn't seem to persist (it normally does, but antivirus / cleanup tools
    sometimes clear netsh state).
#>

$ErrorActionPreference = "Stop"
$PluginPort = 9876   # QGIS MCP plugin's own internal port - do not change without
                     # also changing it in the QGIS MCP plugin panel's port spinner.
$ProxyPort  = 19876  # External port WSL actually connects to.

# Self-elevate if not running as Administrator. Deliberately avoids
# WindowsPrincipal/.IsInRole(), which PowerShell's Constrained Language Mode
# (common on managed/locked-down PCs) blocks with "Method invocation is
# supported only on core types in this language mode". `net session` requires
# admin rights to succeed, so its exit code is a CLM-safe elevation check.
net session > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Re-launching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "=== QGIS MCP - Windows-side setup ===" -ForegroundColor Cyan

# 1. Remove any stale single-port proxy (old design: same port as the plugin).
#    This is what causes WinError 10013 on the plugin after a QGIS restart.
Write-Host "`n[1/3] Removing any stale single-port proxy on $PluginPort (old design)..." -ForegroundColor Cyan
netsh interface portproxy delete v4tov4 listenport=$PluginPort listenaddress=0.0.0.0 2>$null | Out-Null

# 2. Dual-port proxy: 0.0.0.0:$ProxyPort -> 127.0.0.1:$PluginPort
Write-Host "`n[2/3] Configuring port proxy: 0.0.0.0:$ProxyPort -> 127.0.0.1:$PluginPort..." -ForegroundColor Cyan
netsh interface portproxy delete v4tov4 listenport=$ProxyPort listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$ProxyPort listenaddress=0.0.0.0 connectport=$PluginPort connectaddress=127.0.0.1
Write-Host "Current portproxy rules:" -ForegroundColor DarkGray
netsh interface portproxy show v4tov4

# 3. Firewall rules: add one for the new proxy port, remove the old one for the plugin port.
Write-Host "`n[3/3] Configuring firewall rules..." -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "QGIS MCP" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName "QGIS MCP 9876" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

$existingRule = Get-NetFirewallRule -DisplayName "QGIS MCP External" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Firewall rule 'QGIS MCP External' already exists, leaving it as-is."
} else {
    New-NetFirewallRule -DisplayName "QGIS MCP External" -Direction Inbound -Protocol TCP -LocalPort $ProxyPort -Action Allow | Out-Null
    Write-Host "Firewall rule 'QGIS MCP External' created (inbound TCP $ProxyPort allowed)."
}

Write-Host "`n=== Done ===" -ForegroundColor Green
Write-Host "Remaining manual steps:"
Write-Host "  1. Open QGIS."
Write-Host "  2. Open the QGIS MCP plugin panel and click 'Start Server' (port $PluginPort - leave it unchanged)."
Write-Host "  3. In WSL, run setup-wsl.sh (in this same folder) to point Claude Code at this machine via port $ProxyPort."
Write-Host ""
Write-Host "You only need to re-run THIS script if Windows was reinstalled, the portproxy" -ForegroundColor DarkGray
Write-Host "rules were cleared, the firewall rule was removed, or the QGIS MCP plugin fails" -ForegroundColor DarkGray
Write-Host "to start with WinError 10013. It does not need to be re-run just because WSL" -ForegroundColor DarkGray
Write-Host "restarted - only setup-wsl.sh needs that." -ForegroundColor DarkGray
