# Tool coverage & roadmap

*Status: v0.6.1 (2026-07-03) — 110 plugin commands / 108 MCP tools.*

## What is already implemented (110 commands)

| Category | # | Commands |
|---|---|---|
| Session & system | 9 | ping, diagnose, get_qgis_info, get_message_log, list_plugins, get_plugin_info, reload_plugin, get_setting, set_setting |
| Project | 8 | create_new_project, load_project, save_project, get_project_info, get/set_project_variable(s), set_project_crs |
| Layer I/O & management | 16 | add_vector/raster/web_layer, create_memory_layer, remove/duplicate/find_layer, export_layer, layer tree & groups, set_layer_order/visibility/property/crs, get_layer_crs |
| Data inspection | 12 | get_layers, get_layer_info/schema/extent/features, get_field_statistics, get_unique_values, get_raster_info, sample_raster_values, identify_features, get_active_layer, set_active_layer |
| Vector editing | 8 | add/update/delete_features, add/delete/rename_field, field_calculator, add_table_join |
| Selection | 3 | select_features, get_selection, clear_selection |
| Styling & labeling | 7 | set_layer_style, apply/save_style_qml, get/set_layer_labeling, **apply_quantile_style**, **apply_hillshade_context** |
| Expressions & SQL | 3 | validate_expression, evaluate_expression, execute_sql (virtual layers) |
| Processing framework | 11 | list_processing_algorithms, get_algorithm_help, execute_processing(+batch), get_processing_providers, create/list/run models, raster_calculator, zonal_statistics, spatial_join |
| Canvas & navigation | 11 | canvas extent/scale get+set, zoom_to_layer, render_map, get_canvas_screenshot, bookmarks (3), map themes (4) |
| Layouts & reporting | 18 | create_layout, add map/label/legend/scalebar/picture/table items, get_layout_info, list/remove_layouts, export_layout, atlas (configure/export), **create_standard_map_layout**, **duplicate_map_layout**, **find_detail_window**, **save_layout_template** |
| Escape hatches & utility | 4 | **execute_code** (full PyQGIS), batch, transform_coordinates, render_map_base64 |

**Bold** = added by this fork (report-layout toolset).

The three escape hatches — `execute_code` (entire PyQGIS API), `execute_processing`
(~1,000 native/GDAL/GRASS/SAGA algorithms), `execute_sql` — mean *theoretical*
coverage is already near-total. The real gaps are **ergonomics, safety,
discoverability and feedback**: things an AI does badly through a generic escape
hatch, or that cost many error-prone round-trips.

## What is missing (prioritized)

### Tier 1 — safety & state (highest value: AI makes mistakes)
| Proposed tool | Why |
|---|---|
| `begin_edits` / `commit_edits` / `rollback_edits` | Wrap vector edits in an edit session so a bad AI edit is revertible; today `add/update/delete_features` commit immediately. |
| `snapshot_project` / `restore_snapshot` | One-call save-point before risky multi-step operations (styling, layout surgery). |
| `start_task` / `task_status` / `cancel_task` | Async QgsTask wrapper: long Processing runs currently block against a 60 s timeout — big rasters need submit-and-poll. |

### Tier 2 — discovery (critical for shell-less clients like Claude Desktop)
| Proposed tool | Why |
|---|---|
| `list_files(path, pattern)` | Claude Desktop has no shell; it cannot even *find* the user's GeoTIFFs to load. Read-only directory listing closes the gap. |
| `list_db_connections` / `list_db_tables` | Browse registered PostGIS/GeoPackage/Spatialite connections and load from them; `execute_sql` only sees already-loaded layers. |
| `list_style_library` | Enumerate available color ramps, styles, SVG markers — today the AI guesses ramp names ("RdYlGn") and fails on typos. |
| `geocode(place)` | "Zoom to Saskatoon" — resolve a place name to an extent (Nominatim/locator), the single most common navigation ask. |

### Tier 3 — introspection (close the read/write asymmetry)
| Proposed tool | Why |
|---|---|
| `get_layer_style` (structured JSON) | `set_layer_style` exists but reading back the current renderer returns nothing usable — "tweak the existing style" requires seeing it. |
| `get_raster_histogram` | Full-res chunked histogram/percentiles per band; drives honest class breaks without sampling tricks. |
| `get/set_layer_metadata` | Abstract, keywords, attribution — feeds report "data at a glance" tables. |

### Tier 4 — layout completeness
| Proposed tool | Why |
|---|---|
| `load_layout_template` | `save_layout_template` exists; the reverse (instantiate a .qpt with layer/text substitution) does not — templates can be saved but not reused programmatically. |
| `add_layout_html/shape/arrow` | Rich report pages (callout boxes, leader lines) currently need execute_code. |

### Tier 5 — frontier (real QGIS capabilities with zero exposure)
- **Temporal controller** (time-enabled layers, animation export)
- **Mesh & point-cloud layers** (load/inspect/style)
- **3D map views** and 3D exports
- **Plugin installation** (list/reload exist; install does not — security-sensitive, needs elicitation)
- **Georeferencing** (GCP-based raster registration)

## Recommended build order

1. `list_files` — unlocks Claude Desktop as a real GIS assistant (one afternoon).
2. Edit sessions (`begin/commit/rollback_edits`) — makes vector editing safe.
3. `get_layer_style` — symmetric styling, enables "adjust, don't replace".
4. `load_layout_template` — completes the template loop the report workflow already half-uses.
5. Async tasks — removes the 60 s ceiling that blocks basin-scale processing.

Everything in Tiers 1–4 is implementable in the existing handler pattern
(`plugin.py` dispatch + `server.py` bridge tool), no architectural change needed.
