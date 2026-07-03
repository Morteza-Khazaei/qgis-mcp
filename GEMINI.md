# GEMINI.md - QGIS MCP

## Project Overview
**QGIS MCP** connects [QGIS](https://qgis.org/) to [Claude AI](https://claude.ai/) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). It enables LLMs (like Claude) to directly control QGIS — managing layers, editing features, running processing algorithms, rendering maps, and more.

### Architecture
The system consists of two main components communicating over a TCP socket:
1.  **QGIS Plugin** (`qgis_mcp_plugin/`): A standard QGIS plugin that runs a non-blocking TCP socket server (default `localhost:9876`) within QGIS's event loop using a `QTimer`. It processes JSON commands using the PyQGIS API.
2.  **MCP Server** (`src/qgis_mcp/server.py`): A standalone Python process that uses `FastMCP` to expose QGIS operations as MCP tools, resources, and prompts.

**Data Flow:**
`Claude <-> MCP Server (FastMCP) <-> TCP socket <-> QGIS Plugin (PyQGIS) <-> Map Canvas / Project`

---

## Technical Stack
- **Language:** Python 3.12+
- **GIS Platform:** QGIS 3.28–4.x
- **Protocol:** Model Context Protocol (MCP) via `mcp` and `fastmcp` libraries.
- **Package Management:** `uv` (standard for this repo).
- **Socket Protocol:** Length-prefixed JSON framing over TCP (4-byte big-endian uint32 length + JSON).

---

## Development & Operations

### Building and Running
- **Installation:** `python install.py` (Symlinks plugin to QGIS and configures MCP clients).
- **Manual Plugin Setup:** Create a symlink from `qgis_mcp_plugin` to your QGIS profile's `python/plugins/qgis_mcp` folder.
- **Run MCP Server:** `uv run --no-sync src/qgis_mcp/server.py`
- **Run with Compound Tools:** `QGIS_MCP_TOOL_MODE=compound uv run --no-sync src/qgis_mcp/server.py` (Reduces 51 tools to ~19 grouped tools).

### Testing
- **Unit Tests (Mocked Socket):** `uv run --no-sync pytest tests/test_mcp_tools.py -v`
- **Integration Tests (Live QGIS):** `uv run --no-sync pytest tests/test_qgis_live.py -v` (Requires QGIS and the plugin to be running).
- **All Tests:** `uv run --no-sync pytest tests/ -v`

---

## Development Conventions

### Code Style & Quality
- **Linter/Formatter:** Ruff (configured in `pyproject.toml`). Run with `uv run ruff check .` or `uv run ruff format .`.
- **Target Version:** Python 3.12.
- **QGIS Compatibility:** Use `qgis_mcp_plugin/compat.py` for cross-version (QGIS 3 vs 4) enum and constant compatibility. Avoid using raw QGIS enums directly if they differ between versions.
- **Tool Definitions:** Define MCP tools in `src/qgis_mcp/server.py` using `async def`. Use `title`, `description`, and `ToolAnnotations` (`readOnly`, `destructive`, `idempotent`) for all tools.

### Contribution Guidelines
- **Focused PRs:** Keep PRs focused on a single change.
- **Commit Messages:** Write clear, descriptive commit messages.
- **Documentation:** Update `README.md` or `CLAUDE.md` if behavior changes.
- **Security:** Be extremely cautious when modifying `execute_code` as it runs arbitrary PyQGIS code.
- **Versioning:** Always bump both `pyproject.toml` and `qgis_mcp_plugin/metadata.txt` versions together.

### Key Features & Modernizations
- **Large Result Caching**: Tools like `get_layer_features` with `limit > 20` automatically cache results as MCP Resources (`qgis://cache/{id}`) to preserve LLM context.
- **Semantic Error Hints**: The server provides actionable hints for common errors (e.g., "layer not found" suggest calling `get_layers`).
- **Web Layer Support**: First-class support for XYZ, WMS, and WFS layers via `add_web_layer`.
- **Field & Join Management**: Tools for `add_field`, `delete_field`, `rename_field`, and `add_table_join`.
- **Layout & Style**: Basic layout creation (`create_layout`, `add_layout_map`) and QML style management (`apply_style_qml`, `save_style_qml`).

### Key Files & Locations
- `qgis_mcp_plugin/plugin.py`: Main QGIS plugin logic and socket command handlers.
- `src/qgis_mcp/server.py`: MCP server implementation and tool definitions.
- `src/qgis_mcp/client.py`: Standalone socket client for direct QGIS communication.
- `src/qgis_mcp/helpers.py`: Shared utilities for the MCP server.
- `qgis_mcp_plugin/compat.py`: QGIS 3/4 compatibility layer.

### Versioning
Two files **must** be kept in sync when updating the version:
1.  `pyproject.toml` (`version`)
2.  `qgis_mcp_plugin/metadata.txt` (`version`)

---

## Key Concepts
- **Destructive Tools:** Tools like `remove_layer`, `delete_features`, or `execute_code` should use `ctx.elicit()` for user confirmation when supported.
- **Long-running Tools:** Tools like `execute_processing` or `render_map` use `ctx.info()` to report progress back to the MCP client.
- **Compound Tools:** A mode to group granular tools into logical buckets to reduce the schema size for LLMs with limited context or tool-calling capabilities.
- **Feature Format:** Features are returned as flat dictionaries with a `_fid` field and optional `_geometry` (WKT or GeoJSON).
