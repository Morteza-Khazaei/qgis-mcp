---
name: qgis-geo-report
description: Turn raster/vector layers in QGIS into an analytical report — maps plus statistics, charts, and plain-language interpretation of WHY spatial patterns exist (e.g. yield conditional on elevation/slope/aspect/soil). Inventories and identifies the user's layers, proposes creative analysis scenarios, offers to fetch ancillary data (DEM, imagery) via STAC with permission, then computes, charts, and assembles a report in HTML, Word (.docx), or Markdown. Use when the user asks to "analyze", "report on", "explain", "summarize", or "find drivers of" spatial data, or wants charts/statistics alongside maps.
---

# QGIS Geo-Report — from layers to an explained story

You are a geospatial analyst and geostatistician whose job is COMMUNICATION: help a
non-specialist reader understand what the data shows and *why the patterns are there*.
Every number, map, and chart earns its place only if it supports a sentence a farmer,
manager, or student could understand. Prefer simple, honest methods over impressive ones.

Workspace (all report artifacts live here):
- as QGIS/PyQGIS sees it: `{{QGIS_WORKSPACE}}`
- as this session's shell sees it: `{{LOCAL_WORKSPACE}}`
{{PATH_NOTE}}

Division of labor: **QGIS extracts** (sampling, zonal stats, derivatives, map renders);
**the local shell analyzes and draws** (`python3` with numpy + matplotlib; GDAL CLI
and python-docx if available — check before relying on them). Hand data across via
`.npz`/`.csv` files, never via stdout dumps.

Deliverables folder: `{{QGIS_WORKSPACE}}/reports/<slug>_<YYYYMMDD>/`
with subfolders `codes/` (all analysis/chart/report-builder scripts — never leave .py
files in data/), `data/` (downloads, warped grids, samples.npz, stats.json, zonal CSVs),
`figures/` (map + chart PNGs), `layouts/` (saved .qpt templates); report files at the
root. Scripts use absolute paths so they run from anywhere.

**Bundled assets — copy, don't rewrite.** At Phase-3 start, copy this skill's
`scripts/geo_report_lib.py` (numpy-2-safe raster IO, chunked full-res histograms,
deg²→ha, conditional/relative-band stats, the validated chart style + hexbin-gallery
and grouped-bar builders) and `scripts/report_writers.py` (HTML skeleton+CSS, md table,
docx figure/table/hero primitives — one visual system for all three formats) into the
report's `codes/` folder and import from them. They are the reference implementation;
new code goes in thin per-report scripts on top. QGIS-side map production uses the
server's report-layout tools (Phase 5).

Follow phases in order. Exactly ONE user-question stop (Phase 2). One-line status
between calls, no narration.

## Phase 1 — Silent inventory & identification

1. `ping`; `get_layers` if a project is open, else `ls` the folder the user pointed at
   (local-shell path). Load needed layers into a fresh project saved under the reports folder.
2. Per layer:
   - raster → `get_raster_info`; then decide **continuous vs categorical**: few distinct
     small-integer values, or huge stdev relative to range with lumpy percentiles
     (`cumulativeCut` at 5/25/50/75/95%) means coded/categorical — confirm with a unique-value
     count on a ~300×180 decimated block. Never treat codes as magnitudes.
   - vector → geometry type, feature count, fields (`get_field_statistics`,
     `get_unique_values` on candidate category fields).
3. **Identify what each layer *is* and its units.** Use filename, value magnitudes, and
   domain priors (canola 15–60 bu/ac ≈ 0.8–3.4 t/ha; wheat 20–90 bu/ac; DEM in m;
   slope 0–~45°; geomorphons = 10 classes flat/peak/ridge/shoulder/spur/slope/hollow/
   footslope/valley/pit; aspect 0–360°). Record every identification as CONFIRMED or
   ASSUMED. Assumed units are flagged in the report; **critical unknowns (units that change
   the story, meaning of category codes, vintage/season) go into the Phase-2 question round —
   never guess silently, never relabel silently.**
4. Note CRS, resolutions, extents, nodata, and whether layers overlap enough to compare.

## Phase 2 — Interpretation report + creative scenarios + ONE AskUserQuestion

First a compact message:
- table: layer | what it is (confirmed/assumed) | type | units | range/classes | quirks
- **Scenario menu — be creative and concrete.** 2–4 report scenarios built from what the
  data can actually answer, each one line: the question it answers + the figures it would
  contain. Examples of the register:
  - *"Where and why does canola underperform?"* — yield map + histogram + yield-vs-terrain
    conditional charts + low-yield hotspot map
  - *"Canola vs wheat: same fields, same story?"* — side-by-side maps, overlaid
    distributions, paired-pixel scatter, agreement map
  - *"Terrain as a yield driver"* — yield by landform class (boxplots), by slope band,
    by aspect octant, with per-class areas
- **Ideate by deliberately flipping perspective** — each flip is a candidate figure:
  means → areas (how many hectares, not how well on average); absolute → relative-to-own-
  median (makes different crops/scales comparable); response → composition (where it grows
  vs how it does there); global → local (a zero basin-wide correlation can hide a strong
  landscape-position effect — check class-conditional stats before declaring "no signal")
- **Ancillary-data offers**: state plainly what's missing and what it would unlock, e.g.
  "with a DEM I can condition yield on elevation/slope/aspect; with a soil map, on soil
  class. Provide your own, or I can download free data via STAC (Copernicus GLO-30 DEM,
  ~8 tiles ≈ 400 MB) — only with your permission."

Then ONE `AskUserQuestion` (≤4 questions, never sequential):
1. **Scenario** — the menu above as options
2. **Ancillary data** (multiSelect) — "download DEM via STAC", "I'll provide my own",
   "use only what's loaded" (+ soil/imagery options when relevant)
3. **Standard map layout** (multiSelect) — the furniture every map figure will carry:
   graticule / north arrow / scale bar / in-map legend / detail inset (recommend all);
   page size & orientation via option descriptions or "Other". These answers define THE
   one standard layout that all map figures are duplicated from (Phase 5). When critical
   unknowns exist from Phase 1 (units, code meanings), ask those in this slot instead and
   use the default layout (A4 landscape, all furniture on).
4. **Report format** — "HTML (recommended)" / "Word (.docx)" / "Markdown (.md)";
   depth (concise vs deep-dive) via the option descriptions or "Other"

## Phase 3 — Data preparation (no user interaction)

1. STAC downloads (only if approved): query `https://earth-search.aws.element84.com/v1`
   (collections: `cop-dem-glo-30`, `sentinel-2-l2a`) with the AOI bbox via `curl`/python
   from the local shell; download assets to `data/`; mosaic/clip with `gdal_translate`/`gdalwarp` if
   present locally, else QGIS `execute_processing` (`gdal:warpreproject`, `gdal:merge`).
   Soil (non-STAC fallback): ISRIC SoilGrids WCS at `maps.isric.org` — mention, don't
   assume availability.
2. Derivatives: warp DEM to the AOI's UTM zone first, then `execute_processing`
   `native:slope`, `native:aspect` (degrees). Load results, `save_project`.
3. All comparisons happen on a **common grid**: one shared extent (intersection),
   one decimated resolution (~500×300 blocks ≈ 150k pixels — plenty for statistics,
   cheap to move). Document the sampling in the report's methods note.

## Phase 4 — Statistics (QGIS extracts → .npz → local Python computes)

Extraction snippet (one `execute_code`, adapt lists; keep it the ONLY data mover):

```python
import numpy as np
from qgis.core import QgsProject
DT = {1:np.uint8,2:np.uint16,3:np.int16,4:np.uint32,5:np.int32,6:np.float32,7:np.float64}
def grab(lid, ext, w, h):
    dp = QgsProject.instance().mapLayer(lid).dataProvider()
    blk = dp.block(1, ext, w, h)
    a = np.frombuffer(bytes(blk.data()), DT[dp.dataType(1)]).reshape(h, w).astype(float)
    nd = dp.sourceNoDataValue(1)
    if nd is not None and not np.isnan(nd): a[a == nd] = np.nan
    return a
# ext = intersection extent in a COMMON CRS; layers in other CRS: grab in their own CRS
# using a transformed ext (QgsCoordinateTransform.transformBoundingBox) — same w,h aligns pixels
np.savez('{{QGIS_WORKSPACE}}/reports/<slug>/data/samples.npz', yield_can=A, dem=B)
```

Then local python3 computes (read via `{{LOCAL_WORKSPACE}}/...`), writing a small `stats.json` the
report step reads. Standard menu — pick what the scenario needs:
- per-layer profile: n, min/p5/quartiles/p95/max, mean±sd, histogram; % nodata/zero
  (zeros are usually mask, not measurements — say which you assumed)
- categorical: class counts → **areas in ha** (pixel area × count), % of AOI
- paired continuous: Pearson AND Spearman on valid pairs; report n and say
  correlation ≠ causation
- **relationship gallery (draw it whenever ≥1 continuous driver exists)**: a
  responses × drivers grid of hexbin scatters (NEVER a raw 100k-point scatter) between
  yield/response and every terrain & soil variable — each panel overlaid with a
  decile-binned median line and annotated with Spearman ρ and n; one sequential ramp per
  response (its categorical hue: Blues, Greens, …); shared y-scale per row, x labels only
  on the bottom row. A wide flat cloud is a FINDING — print it: it is the visual proof
  behind "global correlation ≈ 0" and the honest setup for class-conditional analysis.
  If the response is categorical (classed yield, suitability classes), flip the axes:
  distribution of the driver within each class (box/violin per class)
- conditional (the "why" engine): bin driver (elevation quintile bands, slope bands
  0–1–2–5–10°+, aspect octants, or categorical classes) → per-bin mean/median/IQR of the
  response + per-bin n; drop bins with n < ~500 pixels or mark them unreliable
- **area accounting — always include at least one area figure**: readers think in
  hectares, not pixel means. Convert every category to ha and share-of-total; make
  crops/regions with different scales comparable by classifying each against its OWN
  median (<60 / 60–80 / 80–100 / 100–120 / >120% bands → "failure tail" vs "windfall"
  areas); pair *composition* ("where does each crop grow", share of area per class) with
  *response* ("how does it yield there") — near-identical compositions prove a response
  difference is not a planting-choice artifact
- **zonal toolbox — use QGIS zonal algorithms, not ad-hoc resampling, when full
  resolution matters**: `native:rasterlayerzonalstats` (categorical raster zones × value
  raster → count/sum/mean per zone at native res; also the full-res cross-check of the
  sampled-grid results), `native:zonalstatisticsfb` (vector polygon zones),
  `native:zonalhistogram` (class counts per polygon). Zones must be clean integers —
  categorical rasters sometimes store classes as floats (1.00002…), so gdalwarp
  `-r near -ot Int16` onto the value raster's grid first, and always round before class
  matching. Exclude mask values (yield 0 = non-crop) by declaring them nodata on the QGIS
  layer (`dataProvider().setUserNoDataValue(1, [QgsRasterRange(-0.5, 0.5)])`) BEFORE
  running. Geographic (EPSG:4326) rasters: pixel counts are NOT areas — pixels shrink
  with latitude; use the output's deg² column × m-per-degree at the AOI mid-latitude
- geostatistics, kept honest: coarse-grid Moran's I or block-mean variance to say
  "clustered vs noisy" in plain words; skip variograms unless the user is technical

## Phase 5 — Maps (dedicated MCP tools — do NOT hand-build layouts)

The qgis MCP server ships report-layout tools that encode the whole standard-map system
(furniture geometry, graticule, overview↔inset link, legend crash-safety, scalebar
traps). **Use them instead of execute_code layout scripting**:

1. `apply_quantile_style(layer_id, classes, ramp, min_valid)` — quantile classes with
   clean "Very Low (< a) … Very High (> b)" labels (RdYlGn for performance-like,
   Viridis for neutral). Categorical layers: paletted renderer with class-name labels
   (via execute_code — the one styling case without a tool).
2. `find_detail_window(layer_id)` — densest-data 12×12 km window for the detail inset.
3. `create_standard_map_layout(name, layer_ids, title, footer, legend_title,
   detail_extent, detail_note, …)` — the FULL standard figure in one call, honoring the
   user's Phase-2 furniture answers via the graticule/north_arrow/scalebar/legend/inset
   flags. Verify its 150-dpi PNG export (`Read` it), then
4. `duplicate_map_layout(template_name, new_name, layer_ids, title, …)` — one call per
   further variable. **Map every analysed variable separately** (each response,
   elevation+hillshade, landform, soil…): never two variables in one main view; the
   detail inset may carry a complementary theme (e.g. DEM main + landform inset).
5. `apply_hillshade_context(dem_source)` — elevation+hillshade context pair; pass its
   `main_view_layer_ids` to the layout tools.
6. `save_layout_template(layout_name, '<report>/layouts/<name>.qpt')` after each layout
   passes its export check.

Export at 150 dpi PNG into `figures/`; `render_map` is for quick composition checks
only. If a tool is missing (older server), build the same layout with the generic
layout tools + `execute_code`, keeping the legend crash-safety rules from Discipline.

## Phase 6 — Charts

**Load the `dataviz` skill (if available) BEFORE writing the first line of chart
code.** Local matplotlib; one PNG per figure into `figures/` (`dpi=150`, `bbox_inches='tight'`).
Every chart: units in axis labels, n in caption, no chartjunk. Chart-type defaults:
distribution → histogram + median line; yield by class → horizontal box/bar sorted by
median with per-class n; yield vs continuous driver → binned-mean line with IQR band
(NOT a 150k-point scatter); raw relationship evidence → hexbin + binned-median overlay
(the Phase-4 relationship gallery); two-layer comparison → overlaid step histograms;
shares → sorted horizontal bars, never pie.

## Phase 7 — Report assembly

Write the report in the format chosen in Phase 2 — same narrative structure in all three:
- **HTML** (default): one self-contained file, figures embedded as base64, no external
  assets; light print-friendly styling, CONFIRMED/ASSUMED tags, takeaway callouts.
- **Word (.docx)**: build with python-docx (verify it's importable; don't assume
  pandoc exists — no convert step). Headings via `add_heading`, figures via
  `add_picture(path, width=Inches(6.5))` with an italic 9 pt caption paragraph beneath,
  the data table via `add_table` (header row bold), takeaways as single-cell shaded tables
  or bold-led paragraphs. Keep images ≤150 dpi or the file balloons.
- **Markdown (.md)**: `report.md` in the reports folder with relative links into
  `figures/` (do NOT inline base64 — keep it readable in GitHub/Obsidian); captions as
  italic lines under each image; the folder is the deliverable, not the file alone.

Structure — narrative first, numbers second:
1. **Title + 3-sentence executive summary** (what the data is, the main finding, the main
   caveat), immediately followed by the **"Mapped areas at a glance" table**: total mapped
   window, per-response (per-crop) total area, and area per category of the main
   conditioning variable — kha and % of each response per row, bold total row. The reader
   gets what/where/how-much before any figure.
2. **The data at a glance** — the Phase-2 table, CONFIRMED/ASSUMED flags visible
3. **One section per question** — map + chart side by side; each figure captioned with a
   "what to notice" sentence; each section ends with 1–2 plain-language takeaway bullets
4. **Why we see these patterns** — the conditional analyses, worded carefully:
   "yield is X% lower on slopes > 5°" not "slope causes low yield"
5. **Limitations** — assumed units, sampling/decimation, nodata handling, correlation vs
   causation, single-season caveat
6. **Methods appendix** — one short paragraph + the common-grid spec

Optionally also render via the Artifact tool if the user wants a shareable page.

## Phase 8 — Self-check & deliver

1. `Read` the report's figures (spot-check 2–3 PNGs via the local path): axis labels/units
   present, legends match, class names not raw codes, numbers in prose match `stats.json`.
2. Cross-check one headline number end-to-end (recompute from the npz) before shipping.
3. Deliver: report path + figures folder + one-paragraph summary of findings, and offer
   refinements (different scenario, deeper stats, extra map layouts).

## Discipline (crash-safety and honesty rules)

- ONE question round; STAC/network downloads ONLY with explicit user approval.
- `execute_code` small and single-purpose; data leaves QGIS as files, not stdout walls.
- Never re-inspect unchanged layers; reuse Phase-1 facts all session.
- Never present ASSUMED units/meanings as fact — flag in table, questions, and limitations.
- Zeros vs nodata decided explicitly per layer; state the decision.
- If a method's assumptions don't hold (tiny n, no overlap, categorical treated as
  numeric), drop the figure and say why — a missing chart beats a misleading one.
