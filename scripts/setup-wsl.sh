#!/usr/bin/env bash
# WSL-side setup for QGIS MCP <-> Windows connectivity.
#
# Run this from WSL every time you start a fresh WSL session (e.g. after
# `wsl --shutdown` or a reboot) — the IP WSL sees for the Windows host can
# change across restarts under WSL2's default NAT networking. This script
# re-detects that IP and re-registers the "qgis" MCP server with Claude Code
# to use it.
#
# Prerequisite (one-time, on Windows): run setup-windows.ps1 in an elevated
# PowerShell, and make sure the QGIS MCP plugin's "Start Server" button has
# been clicked inside QGIS.
#
# Run this script from the same directory you normally launch `claude` from —
# Claude Code's project-scoped ("local") MCP config is keyed by that directory.
#
# Note: PORT below is the EXTERNAL proxy port set up by setup-windows.ps1
# (19876), not the QGIS MCP plugin's own internal port (9876). The two are
# deliberately different - see setup-windows.ps1's header comment for why
# (using the same port for both caused the plugin to fail with WinError 10013
# after every QGIS restart).

set -euo pipefail

PORT=19876
SERVER_NAME=qgis
REPO_URL="https://github.com/Morteza-Khazaei/qgis-mcp/archive/refs/heads/main.zip"

echo "=== QGIS MCP - WSL-side setup ==="
echo "Running from: $(pwd)"
echo "(This must match the directory you normally open Claude Code in.)"
echo

# 1. Detect the Windows host IP as seen from WSL
echo "[1/4] Detecting Windows host IP..."
WIN_IP="$(ip route show default | awk '{print $3; exit}')"
if [[ -z "${WIN_IP}" ]]; then
    echo "ERROR: could not determine the default gateway IP. Is WSL networking up?" >&2
    exit 1
fi
echo "Windows host IP (from WSL): ${WIN_IP}"
echo

# 2. Make sure uv/uvx is available (needed to launch qgis-mcp-server)
echo "[2/4] Checking for uv/uvx..."
if ! command -v uvx >/dev/null 2>&1; then
    echo "uvx not found — installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uvx >/dev/null 2>&1; then
        echo "ERROR: uvx still not found on PATH after install. Open a new shell and re-run this script." >&2
        exit 1
    fi
fi
echo "uvx: $(command -v uvx)"
echo

# 3. Verify the QGIS plugin socket is actually reachable before touching config
echo "[3/4] Verifying QGIS plugin is reachable at ${WIN_IP}:${PORT}..."
REACHABLE=0
if command -v python3 >/dev/null 2>&1; then
    if python3 - "$WIN_IP" "$PORT" <<'EOF'
import socket, json, struct, sys
host, port = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect((host, port))
    cmd = json.dumps({"type": "ping", "params": {}}).encode("utf-8")
    s.sendall(struct.pack(">I", len(cmd)))
    s.sendall(cmd)
    resp_len = struct.unpack(">I", s.recv(4))[0]
    resp = s.recv(resp_len)
    print(resp.decode())
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    s.close()
EOF
    then
        REACHABLE=1
    fi
else
    timeout 3 bash -c "cat < /dev/null > /dev/tcp/${WIN_IP}/${PORT}" 2>/dev/null && REACHABLE=1
fi

if [[ "${REACHABLE}" -eq 0 ]]; then
    echo
    echo "WARNING: could not reach the QGIS plugin at ${WIN_IP}:${PORT}." >&2
    echo "Continuing to register the MCP server anyway, but tool calls will fail until:" >&2
    echo "  - QGIS is open and the MCP plugin's 'Start Server' has been clicked, AND" >&2
    echo "  - setup-windows.ps1 has been run (as Administrator) on the Windows side." >&2
    echo
else
    echo "OK: QGIS plugin responded."
    echo
fi

# 4. Register/update the Claude Code MCP server config
echo "[4/4] Registering '${SERVER_NAME}' MCP server with Claude Code (host=${WIN_IP})..."
claude mcp remove "${SERVER_NAME}" -s local >/dev/null 2>&1 || true
claude mcp add "${SERVER_NAME}" -s local \
    -e QGIS_MCP_HOST="${WIN_IP}" \
    -e QGIS_MCP_PORT="${PORT}" \
    -- uvx --from "${REPO_URL}" qgis-mcp-server

echo
echo "=== Done ==="
echo "QGIS_MCP_HOST is now set to ${WIN_IP} for this project."
echo "If Claude Code is already running, run /mcp inside it to reconnect"
echo "(or restart Claude Code) so it picks up the new setting."
