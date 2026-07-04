# QGIS MCP

Connect [QGIS](https://qgis.org/) to [Claude AI](https://claude.ai/) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), enabling Claude to directly control QGIS — manage layers, edit features, run processing algorithms, render maps, and more.

102 MCP tools covering layer management, feature editing, processing, rendering, styling, layout & atlas authoring, cross-layer SQL, plugin development, and system management. Compatible with QGIS 3.28–4.x. Works with Claude Code, Codex CLI, Gemini CLI, opencode, Claude Desktop, Cursor, VS Code, Windsurf, Zed, and more.

## Architecture

```
Claude ←→ MCP Server (FastMCP) ←→ TCP socket ←→ QGIS Plugin (QTimer) ←→ PyQGIS API
```

1. **QGIS Plugin** (`qgis_mcp_plugin/`) — Runs inside QGIS. Non-blocking TCP socket server that processes JSON commands within QGIS's event loop.
2. **MCP Server** (`src/qgis_mcp/server.py`) — Runs outside QGIS. Exposes QGIS operations as MCP tools via [FastMCP](https://gofastmcp.com/).

## Installation

No clone needed. Requires QGIS 3.28+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

### 1. Install the QGIS plugin

In QGIS: `Plugins` > `Manage and Install Plugins` > search **QGIS MCP** > Install.

Restart QGIS and click **Start Server** in the QGIS MCP dock widget.

### 2. Connect your coding agent

<details>
<summary>Claude Code</summary>

```bash
claude mcp add -s user qgis -- uvx --from https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip qgis-mcp-server
```

Scope reference:

| Flag | Stored in | Visible to |
|------|-----------|-----------|
| `-s local` (default) | `.mcp.json` (gitignored) | You, this project |
| `-s project` | `.mcp.json` (committed) | Whole team, this project |
| `-s user` | `~/.claude.json` | You, every project |

</details>

<details>
<summary>Codex CLI</summary>

```bash
codex mcp add qgis -- uvx --from https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip qgis-mcp-server
```

Or edit `~/.codex/config.toml` directly:

```toml
[mcp_servers.qgis]
command = "uvx"
args = ["--from", "https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip", "qgis-mcp-server"]
```

</details>

<details>
<summary>Gemini CLI</summary>

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["--from", "https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip", "qgis-mcp-server"]
    }
  }
}
```

</details>

<details>
<summary>opencode</summary>

Add to `opencode.json` at your project root:

```json
{
  "mcp": {
    "qgis": {
      "type": "local",
      "command": ["uvx", "--from", "https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip", "qgis-mcp-server"],
      "enabled": true
    }
  }
}
```

</details>

<details>
<summary>Claude Desktop, Cursor, VS Code, Windsurf, and others</summary>

Add to your client's MCP config file:

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": [
        "--from", "https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip",
        "qgis-mcp-server"
      ]
    }
  }
}
```

</details>

## Usage

1. **Start the plugin** — In QGIS, click the MCP toolbar button (or `Plugins` > `QGIS MCP`) and click "Start Server"
2. **Talk to Claude** — The MCP tools will appear automatically. Ask Claude to work with your QGIS project.

### Example prompt

```
You have access to QGIS tools. Do the following:
1. Ping to check the connection
2. Create a new project and save it at "/tmp/my_project.qgz"
3. Load the vector layer "world_map.gpkg" available in Qgis ("resources/data/world_map.gpkg")
4. Filter "USA" from the field "adm0_a3"
6. Render the map and show me the result
7. Save the project
```

## QGIS on Windows, client in WSL2?

`localhost` in WSL2 does **not** reach Windows under default NAT networking, and the
upstream plugin only binds `127.0.0.1`. This fork adds an **"Allow external
connections (bind 0.0.0.0)"** checkbox in the plugin's toolbar dropdown — enable it,
open the firewall for the plugin port, and point `QGIS_MCP_HOST` at the Windows host
IP. Full walkthrough (including the `netsh` dual-port proxy fallback for upstream
builds, the `WinError 10013` trap, and automation scripts `scripts/setup-windows.ps1`
+ `scripts/setup-wsl.sh`): **[docs/WSL_SETUP.md](docs/WSL_SETUP.md)**.

## Claude Code skills (optional)

The repo bundles agent skills under `claude_skills/` that teach Claude Code guided
workflows on top of the MCP tools:

- **qgis-geo-report** — turn raster/vector layers into an analytical report: layer
  inventory and unit identification, one questionnaire round (scenario, ancillary
  data via STAC, standard map layout furniture, output format), then statistics
  (zonal areas, conditional "why" analyses, hexbin relationship galleries), maps
  built with the server's report-layout tools, and a self-contained HTML / Word /
  Markdown report. Ships helper libraries (`geo_report_lib.py`, `report_writers.py`)
  that each report copies into its `codes/` folder for reproducibility.

Install them during setup — the installer asks interactively, or:

```bash
python install.py --non-interactive --skills --qgis-workspace ~/qgis-work
# QGIS on Windows but Claude Code in WSL? Give both views of the same folder:
python install.py --non-interactive --skills \
    --qgis-workspace "C:/Users/me/qgis-work" --local-workspace /mnt/c/Users/me/qgis-work
```

Skills are **copied** (not symlinked — Claude Code's skill scanner doesn't follow
symlinked directories) into `~/.claude/skills/`, with workspace paths rendered into
`SKILL.md` at install time. Re-run the command after a `git pull` to update;
`--uninstall` removes them.

## Updating

The plugin (inside QGIS) and the MCP server (outside QGIS) must stay in sync — a newer server sending a command the older plugin doesn't know will return an error. Run `diagnose` after any update to verify both sides match.

| Component | Remote install | Local install (`git clone`) |
|-----------|---------------|----------------------------|
| **QGIS plugin** | `Plugins` > `Manage and Install Plugins` > Update | Same — Plugin Manager picks up the new version from QGIS Hub |
| **MCP server** | uvx caches the downloaded archive — force an update with `uvx --refresh-package qgis-mcp --from https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip qgis-mcp-server`, then restart your MCP client | `git pull` then restart the MCP server process |

To auto-update instead, add `--refresh-package qgis-mcp` before `--from` in the configs above: uvx then re-resolves this package from GitHub on every launch. **Warning:** this requires network at launch — the MCP server fails to start when offline — and adds ~1–3s to startup. The plain configs above use the cached version and work offline.

After updating the plugin, click **Stop / Start** in the QGIS MCP dock widget (or reload via `Plugins` > `QGIS MCP` > `Reload Plugin`) to load the new code without restarting QGIS.

## Tools (102)

| Category | Tools |
|----------|-------|
| **Project** | `load_project`, `create_new_project`, `save_project`, `get_project_info` |
| **Layers** | `get_layers`, `add_vector_layer`, `add_raster_layer`, `remove_layer`, `find_layer`, `create_memory_layer`, `set_layer_visibility`, `zoom_to_layer`, `get_layer_extent`, `set_layer_property` |
| **Features** | `get_layer_features`, `add_features`, `update_features`, `delete_features`, `select_features`, `get_selection`, `clear_selection`, `get_field_statistics` |
| **Styling** | `set_layer_style` (single, categorized, graduated) |
| **Rendering** | `render_map`, `get_canvas_screenshot`, `get_canvas_extent`, `set_canvas_extent` |
| **Processing** | `execute_processing`, `list_processing_algorithms`, `get_algorithm_help`, `create_processing_model` |
| **Layouts** | `list_layouts`, `export_layout`, `create_layout`, `add_layout_map`, `add_layout_label`, `add_layout_legend`, `add_layout_scalebar`, `add_layout_picture`, `add_layout_table`, `get_layout_info`, `remove_layout` |
| **Atlas** | `configure_atlas`, `export_atlas` |
| **Query** | `execute_sql`, `evaluate_expression`, `identify_features` |
| **Layer tree** | `get_layer_tree`, `create_layer_group`, `move_layer_to_group`, `duplicate_layer`, `set_layer_order` |
| **Plugins** | `list_plugins`, `get_plugin_info`, `reload_plugin` |
| **System** | `ping`, `diagnose`, `get_qgis_info`, `get_raster_info`, `get_message_log`, `execute_code`, `batch_commands`, `validate_expression`, `get_project_variables`, `set_project_variable`, `get_setting`, `set_setting`, `transform_coordinates` |

All tools are async with human-readable titles and annotations (`readOnly`, `destructive`, `idempotent`). Destructive tools ask for confirmation via MCP elicitation when supported; clients without elicitation proceed normally (fail-open) since tools are already gated by `ToolAnnotations`. Long-running tools report progress via MCP logging.

### Compound tool mode

Set `QGIS_MCP_TOOL_MODE=compound` to reduce the granular tools to ~23 grouped tools, cutting schema overhead per LLM turn. Each compound tool takes an `action` parameter:

```bash
QGIS_MCP_TOOL_MODE=compound uv run --no-sync src/qgis_mcp/server.py
```

Groups: `system`, `project`, `layer`, `features`, `selection`, `style`, `canvas`, `render`, `processing`, `code`, `batch`, `layer_tree`, `plugins`, `variables`, `settings`, `expression`, `transform`, `message_log`, `layer_property`.

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `QGIS_MCP_HOST` | `localhost` | Host for socket connection |
| `QGIS_MCP_PORT` | `9876` | Port for socket connection |
| `QGIS_MCP_TOKEN` | _(unset)_ | Optional shared secret. When set, the plugin rejects any command without a matching token. See [Authentication](#authentication). |
| `QGIS_MCP_TRANSPORT` | `stdio` | MCP transport: `stdio` or `streamable-http` |
| `QGIS_MCP_LOG_FILE` | `~/.local/share/qgis-mcp/server.log` | Log file path (empty to disable) |
| `QGIS_MCP_LOG_LEVEL` | `INFO` | File log level |
| `QGIS_MCP_TOOL_MODE` | `granular` | `granular` (102 tools) or `compound` (~23 grouped) |

### Authentication

By default the socket has **no authentication** — it binds to `localhost` only, but any process on the machine that can reach the port can drive QGIS (including `execute_code`, which runs arbitrary PyQGIS). For shared or multi-user machines, set a shared secret so only callers that know it can connect:

1. Set `QGIS_MCP_TOKEN` in the **environment QGIS runs in** (so the plugin enforces it), then Stop/Start the server in the dock. The QGIS log shows `Token authentication ENABLED`.
2. Set the **same** value in the MCP server's environment — add it to the `env` block of your MCP client config:

   ```json
   {
     "mcpServers": {
       "qgis": {
         "command": "uvx",
         "args": ["--from", "https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip", "qgis-mcp-server"],
         "env": { "QGIS_MCP_TOKEN": "your-long-random-secret" }
       }
     }
   }
   ```

The token is compared in constant time. When `QGIS_MCP_TOKEN` is unset (the default), behaviour is unchanged. This raises the bar against other local users/processes; a process running as the same user can still read the token from your config, so it is not a sandbox.

## Contributing

```bash
git clone https://github.com/nkarasiak/qgis-mcp.git
cd qgis-mcp
python install.py   # symlinks plugin + configures your MCP client
```

`install.py` options: `--clients claude-desktop,cursor`, `--remote` (uvx instead of uv run), `--profile myprofile`, `--uninstall`.

> **Windows (Microsoft Store / MSIX Claude Desktop):** `install.py` uses `--directory` instead of `cwd` in generated configs. This is required for Store-installed Claude Desktop, which runs MCP servers in an MSIX sandbox that silently drops `cwd`. If you configure manually, use `uv --directory "/path/to/qgis-mcp" run --no-sync src/qgis_mcp/server.py` — this works on both MSIX and standalone installs. You can identify a Store install when the config file is under `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\` instead of `%APPDATA%\Claude\`.

```bash
# Unit tests (no QGIS needed — mocked socket)
uv run --no-sync pytest tests/test_mcp_tools.py -v

# Integration tests (requires QGIS plugin running)
uv run --no-sync pytest tests/test_qgis_live.py -v
```

## License

This project is licensed under the GNU GPL v2 or later.
