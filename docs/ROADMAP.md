# Tool coverage & roadmap

*Status: v0.7.0 (2026-07-03) — 119 plugin commands / 117 MCP tools.*

## What is already implemented (119 commands)

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
| Proposed tool | Status |
|---|---|
| `begin_edits` / `commit_edits` / `rollback_edits` | **DONE (0.7.0)** — feature edits route through the edit buffer during a session (`buffered: true` in responses) and are revertible. |
| `snapshot_project` / `restore_snapshot` | Open — one-call save-point before risky multi-step operations. |
| `start_processing_task` / `task_status` / `cancel_task` | **DONE (0.7.0)** — background QgsTask with progress/log polling; result layers auto-added to the project. |

### Tier 2 — discovery (critical for shell-less clients like Claude Desktop)
| Proposed tool | Why |
|---|---|
| `list_files(path, pattern)` | **DONE (0.7.0)** — read-only listing (name/type/size/mtime). |
| `list_db_connections` / `list_db_tables` | Browse registered PostGIS/GeoPackage/Spatialite connections and load from them; `execute_sql` only sees already-loaded layers. |
| `list_style_library` | Enumerate available color ramps, styles, SVG markers — today the AI guesses ramp names ("RdYlGn") and fails on typos. |
| `geocode(place)` | "Zoom to Saskatoon" — resolve a place name to an extent (Nominatim/locator), the single most common navigation ask. |

### Tier 3 — introspection (close the read/write asymmetry)
| Proposed tool | Why |
|---|---|
| `get_layer_style` (structured JSON) | **DONE (0.7.0)** — renderer type, hex colors, categories/ranges, raster class breaks, opacity, labeling state. |
| `get_raster_histogram` | Full-res chunked histogram/percentiles per band; drives honest class breaks without sampling tricks. |
| `get/set_layer_metadata` | Abstract, keywords, attribution — feeds report "data at a glance" tables. |

### Tier 4 — layout completeness
| Proposed tool | Why |
|---|---|
| `load_layout_template` | **DONE (0.7.0)** — instantiates a .qpt with literal text substitution (XML-escaped). |
| `add_layout_html/shape/arrow` | Rich report pages (callout boxes, leader lines) currently need execute_code. |

### Tier 5 — frontier (real QGIS capabilities with zero exposure)
- **Temporal controller** (time-enabled layers, animation export)
- **Mesh & point-cloud layers** (load/inspect/style)
- **3D map views** and 3D exports
- **Plugin installation** (list/reload exist; install does not — security-sensitive, needs elicitation)
- **Georeferencing** (GCP-based raster registration)

## Recommended build order (next)

1. `snapshot_project` / `restore_snapshot` — the remaining Tier-1 safety item.
2. `list_db_connections` / `list_db_tables` — PostGIS/GeoPackage discovery.
3. `list_style_library` + `geocode` — styling and navigation ergonomics.
4. `get_raster_histogram` and layer metadata read/write.

Everything in Tiers 1–4 is implementable in the existing handler pattern
(`plugin.py` dispatch + `server.py` bridge tool), no architectural change needed.
