"""Shared helpers for server.py and compound_tools.py.

Imports only from ``mcp`` and stdlib — no circular-import risk.
"""

import importlib.metadata
import json
import os
import socket
import struct

from mcp.types import Annotations, ImageContent, ResourceLink, TextContent

# ---------------------------------------------------------------------------
# Protocol constants — single source of truth for defaults across all modules
# ---------------------------------------------------------------------------

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
TIMEOUT_DEFAULT = 30  # seconds — most tool commands
TIMEOUT_LONG = 60  # seconds — execute_processing, render_map, execute_code, batch
RECV_CHUNK_SIZE = 65536  # bytes per recv/recv_into call
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB — plugin-side buffer/message limit
HEADER_STRUCT = struct.Struct(">I")  # 4-byte big-endian uint32 length prefix

BATCH_BLOCKED_COMMANDS = frozenset(
    {
        "execute_code",
        "remove_layer",
        "delete_features",
        "set_setting",
        "reload_plugin",
    }
)


def _running_under_wsl():
    """True when this process runs inside Windows Subsystem for Linux."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _wsl_default_gateway():
    """Return the default-gateway IP (the Windows host in WSL2 NAT mode), or None."""
    RTF_GATEWAY = 0x2
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.split()
                if len(fields) < 4:
                    continue
                if fields[1] == "00000000" and int(fields[3], 16) & RTF_GATEWAY:
                    return socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
    except (OSError, ValueError):
        pass
    return None


def resolve_qgis_host(port):
    """Resolve which host the QGIS plugin socket lives on.

    An explicit ``QGIS_MCP_HOST`` always wins (the literal ``auto`` forces
    detection). Outside WSL the answer is simply ``DEFAULT_HOST``. Under WSL2
    the Windows host is *not* loopback in NAT mode, and its gateway IP changes
    across Windows reboots — so probe instead of hardcoding: try localhost
    first (mirrored networking mode, or a QGIS inside WSL), then the default
    gateway (NAT mode). Returns the first candidate that accepts a TCP
    connection; if none do, returns the last candidate so the caller's normal
    connection-error path reports the most likely target.
    """
    env_host = os.environ.get("QGIS_MCP_HOST", "").strip()
    if env_host and env_host.lower() != "auto":
        return env_host
    if not _running_under_wsl():
        return DEFAULT_HOST

    candidates = [DEFAULT_HOST]
    gateway = _wsl_default_gateway()
    if gateway:
        candidates.append(gateway)
    for host in candidates:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return host
        except OSError:
            continue
    return candidates[-1]


def get_auth_token():
    """Return the shared-secret socket token, or ``None`` when auth is disabled.

    Read from the ``QGIS_MCP_TOKEN`` environment variable. When unset or empty,
    authentication is off and behaviour is unchanged — the plugin accepts any
    command (the historical default). When set, the client attaches it to every
    command and the plugin rejects commands that don't present a matching token.
    """
    token = os.environ.get("QGIS_MCP_TOKEN", "").strip()
    return token or None


def enrich_diagnose(result: dict) -> dict:
    """Append server/plugin version-match check to a diagnose result."""
    try:
        server_version = importlib.metadata.version("qgis-mcp")
    except importlib.metadata.PackageNotFoundError:
        server_version = "unknown (editable install?)"

    plugin_version = None
    for check in result.get("checks", []):
        if check["name"] == "plugin_version":
            plugin_version = check.get("detail")
            break

    version_match = "ok" if plugin_version == server_version else "mismatch"
    result["checks"].append(
        {
            "name": "version_match",
            "status": version_match,
            "detail": {"server": server_version, "plugin": plugin_version},
        }
    )
    if version_match == "mismatch" and result["status"] == "healthy":
        result["status"] = "degraded"

    return result


def make_layer_response(result: dict, fallback_name: str = "Layer") -> list:
    """Build [TextContent, ResourceLink] for a layer-mutating tool response."""
    layer_id = result.get("layer_id", result.get("id", ""))
    return [
        TextContent(type="text", text=json.dumps(result)),
        ResourceLink(
            type="resource_link",
            uri=f"qgis://layers/{layer_id}/info",
            name=result.get("name", fallback_name),
        ),
    ]


def make_project_response(result: dict) -> list:
    """Build [TextContent, ResourceLink] for a project-mutating tool response."""
    return [
        TextContent(type="text", text=json.dumps(result)),
        ResourceLink(type="resource_link", uri="qgis://project", name="Project Info"),
    ]


def make_render_response(result: dict, width: int, height: int, path: str | None) -> list:
    """Build [ImageContent, optional TextContent] for a render_map response."""
    content: list = [
        ImageContent(
            type="image",
            data=result["base64_data"],
            mimeType="image/png",
            annotations=Annotations(audience=["user", "assistant"], priority=1.0),
        )
    ]
    if path:
        content.append(
            TextContent(
                type="text",
                text=json.dumps({"saved": path, "width": width, "height": height}),
                annotations=Annotations(audience=["assistant"], priority=0.5),
            )
        )
    return content
