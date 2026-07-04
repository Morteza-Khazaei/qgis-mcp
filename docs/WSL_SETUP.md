# QGIS MCP Server — Installation & Setup

This document describes how to install and configure the **QGIS MCP server** so that
Claude Code (running in **WSL2 / Ubuntu**) can control **QGIS running on Windows**.

The setup has **two halves** that must both be running:

| Half | Where it runs | Role |
|------|---------------|------|
| **QGIS MCP plugin** | Windows (inside QGIS) | Opens a TCP socket QGIS listens on (default port `9876`) |
| **qgis-mcp server** | WSL2 (launched by Claude Code) | Bridges Claude ⇄ the QGIS socket |

Claude talks to the `qgis-mcp` server over stdio; that server dials **out** to the
QGIS plugin's socket over TCP. If the plugin isn't running, tools will fail even if
the MCP server itself shows "Connected".

---

## Preferred fix in THIS fork: the bind-address checkbox (no port proxy)

Plugin **0.6.1+ of this fork** removes the root cause: the toolbar dropdown
(next to the port spinner) has a checkbox **"Allow external connections
(bind 0.0.0.0)"**. Enable it, restart the plugin server, and WSL can connect
straight to the plugin's own port (9876) — no `netsh` portproxy, no dual-port
juggling, no WinError 10013 trap. You still need:

1. A Windows Firewall rule for the plugin port:
   ```powershell
   New-NetFirewallRule -DisplayName "QGIS MCP" -Direction Inbound -Protocol TCP -LocalPort 9876 -Action Allow
   ```
2. The WSL side pointed at the Windows host IP with `QGIS_MCP_PORT=9876`
   (`setup-wsl.sh` handles the IP detection — set `PORT=9876` at the top, or
   leave `19876` if you keep the proxy).
3. Ideally `QGIS_MCP_TOKEN` set on both sides — 0.0.0.0 exposes the socket to
   your LAN, and the token gates every command.

Parts 1.5's portproxy approach below remains fully documented because (a) it is
what you need on the upstream plugin (which hardcodes `localhost`), and (b) it
works without rebinding the plugin socket.

---

## Quick start (use this first)

This folder includes two scripts that automate everything below. Most people should
just use these instead of following Parts 1–2 by hand.

| Script | Where to run it | When |
|--------|------------------|------|
| [`setup-windows.ps1`](../scripts/setup-windows.ps1) | **Windows**, in an elevated (Administrator) PowerShell | Once. Re-run any time the QGIS MCP plugin fails to start with `WinError 10013` (see Part 1.5), or if the portproxy/firewall rules ever get cleared. |
| [`setup-wsl.sh`](../scripts/setup-wsl.sh) | **WSL**, in a regular bash shell | Every time you start a fresh WSL session (e.g. after `wsl --shutdown` or a reboot) — the Windows IP as seen from WSL can change. |

Steps:

1. In QGIS on Windows, open the QGIS MCP plugin panel and click **Start Server**
   (leave QGIS open).
2. In a PowerShell on Windows (does not need to already be elevated — the script
   elevates itself):
   ```powershell
   cd <path-to-this-repo>\scripts
   powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1   # from this repo's scripts/ folder
   ```
   The `-ExecutionPolicy Bypass` is needed because Windows blocks running local
   `.ps1` files by default; this only affects this one invocation, not your
   system-wide policy. (Safe to re-run any time; it's idempotent.)
3. In WSL, from the same directory you normally launch `claude` from:
   ```bash
   bash <path-to-this-repo>/scripts/setup-wsl.sh
   ```
   This detects the current Windows host IP, verifies the QGIS plugin actually
   responds, and re-registers the `qgis` MCP server with Claude Code pointing at
   that IP.
4. In Claude Code, run `/mcp` to reconnect (or restart Claude Code), then confirm
   with a `ping` tool call.

If step 3 reports the plugin isn't reachable, double-check step 1 and 2 first —
`setup-wsl.sh` only configures the WSL/Claude side, it can't start QGIS or open
Windows Firewall for you.

The rest of this document explains what these scripts do under the hood, and how to
do it by hand — read on if you want to understand the setup, troubleshoot something
the scripts don't cover, or the scripts aren't available.

---

## Architecture / network path

```
┌─────────────────── Windows ────────────────────┐      ┌──────────── WSL2 (Ubuntu) ────────────┐
│                                                 │      │                                        │
│   QGIS  +  qgis-mcp plugin                      │      │   Claude Code                          │
│   listening on 127.0.0.1:9876 (fixed, internal) │      │   qgis-mcp-server (uvx)                │
│        ▲                                        │      │   QGIS_MCP_HOST=<windows ip>           │
│        │ netsh portproxy                        │      │   QGIS_MCP_PORT=19876                  │
│   0.0.0.0:19876  ◄──────────TCP 19876───────────┼──────┤                                        │
└──────────────────────────────────────────────────┘      └────────────────────────────────────────┘
```

Because QGIS is on Windows and Claude is in WSL2, `localhost` from WSL does **not**
reach Windows (default NAT networking). We point the server at the Windows host IP.
Note the **two different ports**: the plugin always binds `9876` internally and that
never changes; WSL instead talks to external port `19876`, which a port proxy
forwards to the plugin's `9876`. Part 1.5 explains why these must be different
ports rather than the same one.

---

## Part 1 — Windows side (QGIS plugin)

1. **Install QGIS** (if not already) — https://qgis.org/download/
2. **Install the `qgis-mcp` plugin** into QGIS:
   - The plugin lives in the same repo: https://github.com/Morteza-Khazaei/qgis-mcp
     (folder `qgis_mcp_plugin`).
   - Copy the `qgis_mcp_plugin` folder into your QGIS plugins directory, typically:
     ```
     C:\Users\<you>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp_plugin
     ```
   - Restart QGIS, then enable it via **Plugins → Manage and Install Plugins → Installed → QGIS MCP**.
3. **Start the plugin server** inside QGIS:
   - Open the QGIS MCP panel/dialog and click **Start Server**.
   - Confirm it is listening on port **9876** — check the QGIS log panel for a line like
     `QGIS MCP server started on localhost:9876`.
   - ⚠️ **In the upstream plugin build, the bind address is hardcoded to `localhost`
     (127.0.0.1) and is not configurable from the UI** — only the port is (a
     `port_spin` control). **This fork (0.6.1+) adds an "Allow external
     connections (bind 0.0.0.0)" checkbox in the toolbar dropdown — prefer that
     (see the section above) and skip Part 1.5 entirely.** On upstream builds
     there is no `0.0.0.0` option to select. This means the
     socket only accepts connections from Windows itself; WSL's virtual network
     adapter cannot reach it directly, no matter the firewall state. See Part 1.5
     below for the workaround.
4. **Allow the port through Windows Firewall** (inbound TCP 9876). In an **Admin PowerShell**:
   ```powershell
   New-NetFirewallRule -DisplayName "QGIS MCP 9876" -Direction Inbound -Protocol TCP -LocalPort 9876 -Action Allow
   ```
   Note: this alone is **not sufficient** — a firewall rule only matters if something
   is actually listening on the interface the traffic arrives on. Since the plugin
   listens on `127.0.0.1` only, traffic arriving on the WSL-facing adapter never
   reaches the process regardless of firewall state. Continue to Part 1.5.

---

## Part 1.5 — Bridging WSL to a localhost-only plugin (diagnosis & fix)

This is the failure mode actually hit when connecting from WSL2 to this plugin build,
and how it was diagnosed and resolved without modifying the plugin.

### Diagnosis steps

1. **`ping` tool fails with "Could not connect to QGIS"** even though `claude mcp`
   / `/mcp` shows the `qgis` server itself as "Connected". This is expected and not
   a symptom of a problem — see the note in section 2.3: "Connected" only means the
   stdio MCP server process launched, not that it reached QGIS.
2. **Raw TCP probe from WSL to the Windows gateway IP times out (no RST):**
   ```bash
   ip route show default   # gateway IP = Windows host IP, e.g. 192.168.32.1
   timeout 3 bash -c 'cat < /dev/null > /dev/tcp/192.168.32.1/9876' && echo OPEN || echo "CLOSED/FILTERED"
   ```
   A **timeout** (no immediate RST) points to either "nothing listening on that
   interface" or "firewall silently dropping" — as opposed to an instant
   **"connection refused"**, which means a host answered but nothing was on that
   port.
3. **Probing `127.0.0.1:9876` from WSL itself returns "connection refused" instantly**
   — confirming nothing listens on WSL's own loopback (expected; the plugin runs on
   Windows, not WSL).
4. **Check the QGIS message log** for the exact bind line:
   ```
   QGIS MCP server started on localhost:9876
   ```
   This confirms the plugin bound to `127.0.0.1` specifically, not `0.0.0.0` —
   the root cause. Reading the plugin source (`qgis_mcp_plugin/plugin.py`) confirms
   `_DEFAULT_HOST = "localhost"` is hardcoded and never overridden; only `port` is
   read from the UI spin box.
5. **Conclusion:** the firewall rule from step 4 (Part 1) was necessary but not
   sufficient. The fix has to make something listen on an interface WSL can reach,
   since the plugin itself won't bind there.

### A second failure mode: same-port proxy causes `WinError 10013` on QGIS restart

The first version of the fix below used a **single-port** proxy: forward
`0.0.0.0:9876` to `127.0.0.1:9876` — i.e. the exact same port number the plugin
itself binds to. This worked initially, but broke the next time QGIS was closed
and reopened:

```
CRITICAL    Failed to start server: [WinError 10013] An attempt was made to
            access a socket in a way forbidden by its access permissions
INFO        QGIS MCP server stopped
```

**Root cause:** the single-port proxy only "worked" because it was set up
*after* the plugin had already bound port 9876 — the proxy just forwarded to an
already-open socket. But the portproxy rule itself permanently reserves port 9876
at the OS level. The moment QGIS restarts and the plugin tries to **rebind**
`127.0.0.1:9876`, Windows sees the port already exclusively claimed by the
portproxy rule and refuses the bind — hence `WinError 10013`. This is a
bind-ordering trap, not a one-off glitch: it recurs on every QGIS restart as
long as the same-port proxy rule exists.

**Fix: use a different external port than the plugin's internal port (dual-port
proxy).** The plugin keeps its own port (9876) entirely to itself; WSL instead
connects to a distinct external port (19876), which a portproxy rule forwards to
the plugin's real `127.0.0.1:9876`. Since the two port numbers never collide,
the plugin can always rebind 9876 freely regardless of proxy state.

`setup-windows.ps1` (see Quick start) automates this and also cleans up any
stale single-port rule automatically — prefer running that script. If the QGIS
MCP plugin ever fails to start with `WinError 10013` again, re-run it.

### Fix: dual-port `netsh` proxy (no plugin changes, no WSL restart, survives QGIS restarts)

If you previously set up the old single-port version, remove it first (do this
any time the plugin fails to start with `WinError 10013` — it means a stale
same-port proxy rule is holding the port):

```powershell
netsh interface portproxy delete v4tov4 listenport=9876 listenaddress=0.0.0.0
```

Then, in an **Admin PowerShell** on Windows, create the dual-port proxy:

```powershell
netsh interface portproxy add v4tov4 listenport=19876 listenaddress=0.0.0.0 connectport=9876 connectaddress=127.0.0.1
netsh advfirewall firewall add rule name="QGIS MCP External" dir=in action=allow protocol=TCP localport=19876
```

This forwards any inbound connection on port **19876** (on any interface,
including the WSL virtual adapter) to the plugin's real loopback-bound listener
on **9876**. WSL now connects to `19876`, never to `9876` directly.

To remove it later:

```powershell
netsh interface portproxy delete v4tov4 listenport=19876 listenaddress=0.0.0.0
```

### Verifying the fix from WSL

Test the raw QGIS MCP wire protocol directly (length-prefixed JSON over TCP),
bypassing the Claude MCP tool entirely:

```bash
python3 - <<'EOF'
import socket, json, struct
HOST, PORT = "192.168.32.1", 19876  # your Windows gateway IP + the external PROXY port (not the plugin's own 9876)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
s.connect((HOST, PORT))
cmd = json.dumps({"type": "ping", "params": {}}).encode("utf-8")
s.sendall(struct.pack(">I", len(cmd)))
s.sendall(cmd)
resp_len = struct.unpack(">I", s.recv(4))[0]
print(s.recv(resp_len).decode())
s.close()
EOF
```

Expected output: `{"status": "success", "result": {"pong": true}}`. Once this works,
retry the `ping` MCP tool in Claude — it should now succeed too.

### Alternative fix considered: WSL2 mirrored networking

Instead of the port proxy, enabling `networkingMode=mirrored` in `.wslconfig` (see
section 2.2) makes WSL share Windows' network namespace directly, so `localhost`
means the same thing on both sides — no port proxy, gateway IP, or dual-port
juggling needed at all. This is arguably cleaner long-term, but requires
`wsl --shutdown` (drops the current WSL session, including any running Claude
Code instance) and a compatible Windows 11 / WSL version. The port-proxy approach
was chosen instead because it requires no WSL restart and works immediately.

---

## Part 2 — WSL side (qgis-mcp server + Claude Code)

### 2.1 Install `uv` / `uvx`

The server is launched with `uvx`. Install `uv` (which provides `uvx`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This installs to `~/.local/bin` and adds it to `~/.profile` and `~/.bashrc`.
Verify:

```bash
uv --version
uvx --version
```

### 2.2 Find the Windows host IP (from WSL)

Under default WSL2 NAT networking, get the Windows host IP with:

```bash
ip route show default | awk '{print $3}'
```

> ⚠️ This IP (e.g. `172.30.144.1`) **can change after a reboot**. If the connection
> breaks later, re-run this and update `QGIS_MCP_HOST` (see 2.4).
>
> Alternative: enable WSL2 **mirrored networking** (Windows 11) so you can use
> `localhost` instead of the IP. Add to `C:\Users\<you>\.wslconfig`:
> ```ini
> [wsl2]
> networkingMode=mirrored
> ```
> then run `wsl --shutdown` in PowerShell and restart WSL. With mirrored mode set
> `QGIS_MCP_HOST=localhost`.

### 2.3 Register the MCP server with Claude Code

Run this in the project directory (adds a **local**-scoped server). Replace the IP
with the one from step 2.2:

```bash
claude mcp add qgis -s local \
  -e QGIS_MCP_HOST=172.30.144.1 \
  -e QGIS_MCP_PORT=19876 \
  -- uvx --from "https://github.com/Morteza-Khazaei/qgis-mcp/archive/refs/heads/main.zip" qgis-mcp-server
```

Note: `19876` is the external portproxy port from Part 1.5, **not** the plugin's
own internal port (9876) — see the architecture diagram above.

Verify:

```bash
claude mcp get qgis
```

Expected output includes:

```
Status: ✔ Connected
Type: stdio
Command: uvx
Environment:
    QGIS_MCP_HOST=172.30.144.1
    QGIS_MCP_PORT=19876
```

> "Connected" here only means the MCP **server** launched successfully. The actual
> QGIS connection is lazy — it dials QGIS on the **first tool call**.

### 2.4 Changing the host or port later

Re-register with new values:

```bash
claude mcp remove qgis -s local
claude mcp add qgis -s local \
  -e QGIS_MCP_HOST=<new-ip-or-localhost> \
  -e QGIS_MCP_PORT=<new-port> \
  -- uvx --from "https://github.com/Morteza-Khazaei/qgis-mcp/archive/refs/heads/main.zip" qgis-mcp-server
```

Then **restart Claude Code** for the change to take effect. Note: the same port must
be set on **both** sides — the QGIS plugin server and `QGIS_MCP_PORT`.

---

## Configuration reference

The `qgis-mcp-server` reads these environment variables at connection time:

| Variable | Default | Notes |
|----------|-----------|-------|
| `QGIS_MCP_HOST` | `localhost` | Set to the Windows host IP for WSL→Windows |
| `QGIS_MCP_PORT` | `9876` | Must be an integer 1–65535. **When bridging from WSL via the dual-port proxy (Part 1.5), set this to the external proxy port (`19876`), not the plugin's internal port (`9876`).** |

---

## Startup checklist (each session)

1. ☐ QGIS is open on Windows.
2. ☐ QGIS MCP plugin server is **started** (listening on its internal port 9876).
   If it fails with `WinError 10013`, re-run `setup-windows.ps1` first (Part 1.5).
3. ☐ The dual-port proxy is in place (`netsh interface portproxy show v4tov4`
   should list `19876 -> 127.0.0.1:9876`) and Windows Firewall allows inbound TCP 19876.
4. ☐ `QGIS_MCP_HOST` matches the current Windows IP (`ip route show default`) and
   `QGIS_MCP_PORT` is `19876` (the proxy port, not the plugin's own 9876).
5. ☐ Claude Code (re)started so it picks up the MCP config.
6. ☐ Trigger a tool call in Claude to establish the connection.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ENOENT` on server start | `uvx` not on PATH | Install `uv` (2.1); ensure `~/.local/bin` is on PATH |
| MCP "Connected" but tools time out / refuse connection | QGIS plugin not started, or wrong IP/port | Start plugin; verify IP via `ip route show default`; confirm `QGIS_MCP_PORT=19876` (not 9876) |
| Worked yesterday, broken after reboot | Windows IP changed (NAT mode) | Re-run 2.2 and update `QGIS_MCP_HOST` (2.4), or use mirrored networking |
| Raw TCP probe to Windows gateway IP times out (no refusal) from WSL | Plugin bound to `127.0.0.1` only (this build has no `0.0.0.0` UI option) — see Part 1.5 | Run `setup-windows.ps1` (dual-port proxy, Part 1.5); or switch to WSL2 mirrored networking |
| Raw TCP probe to Windows gateway IP is refused instantly | Nothing listening / plugin not started, or portproxy not yet added | Start the plugin; confirm `netsh interface portproxy show v4tov4` lists `19876 -> 127.0.0.1:9876` |
| **QGIS MCP plugin fails to start: `WinError 10013` in the QGIS log, right after "Start Server"** | A stale **single-port** proxy rule (old design: `0.0.0.0:9876 -> 127.0.0.1:9876`) is exclusively holding port 9876, blocking the plugin's own rebind — see Part 1.5 | Re-run `setup-windows.ps1` — it deletes the stale same-port rule and installs the dual-port (19876→9876) one. Then click "Start Server" in QGIS again. |
| Port already in use | Another process on 9876 or 19876 | Pick new ports on both sides (2.4 + plugin config + `setup-windows.ps1`'s `$PluginPort`/`$ProxyPort`) |

---

## Quick test from WSL

Check whether the QGIS plugin port is reachable from WSL before using Claude tools:

```bash
# Replace IP with your Windows host IP; 19876 is the external proxy port (Part 1.5)
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/172.30.144.1/19876' && echo "OK: port 19876 reachable" || echo "FAIL: cannot reach 19876"
```

If this fails, the problem is on the Windows side (plugin not started, firewall, or
wrong bind address) — not with Claude Code.
