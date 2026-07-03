"""Standard report-map layout tools (qgis-geo-report skill backend).

One standard cartographic layout for every map figure in a report: title,
WGS-84 graticule, large north arrow (top-right, in-view), small km scale bar
(bottom-left, in-view), pruned in-map legend, CRS footer, and an
overview+detail pair — a detail inset whose footprint is drawn on the main
map as a red box. Furniture geometry and the crash-safe legend handling were
tuned interactively; do not "simplify" the pruning code (see comments).

All functions are handler-style: plain kwargs in, JSON-serializable dict out.
"""
import math
import os

from qgis.core import (
    QgsApplication,
    QgsBasicNumericFormat,
    QgsColorRampLegendNodeSettings,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFillSymbol,
    QgsHillshadeRenderer,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendRenderer,
    QgsLegendStyle,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsRectangle,
    QgsSingleBandPseudoColorRenderer,
    QgsStyle,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor, QFont, QPainter

# Furniture geometry (mm) for A4 landscape 297x210 — the tuned reference build.
GEOM = {
    "main_map": (18, 14, 186, 160),
    "inset_map": (212, 14, 76, 76),
    "title": (18, 4, 200, 8),
    "inset_note": (212, 92, 80, 6),
    "footer": (18, 200, 260, 5),
    "legend": (212, 102, 62, 48),
    "scalebar": (22, 164, 70, 12),   # small: slim bar inside main view, bottom-left
    "north": (182, 17, 18, 24),      # large arrow inside main view, top-right
}


def _project():
    return QgsProject.instance()


def _layers(layer_ids):
    proj = _project()
    out = []
    for lid in layer_ids:
        lyr = proj.mapLayer(lid)
        if lyr is None:
            raise ValueError(f"Layer not found: {lid}")
        out.append(lyr)
    return out


def _union_extent_project_crs(layers, grow_m=1500):
    proj = _project()
    ext = None
    for lyr in layers:
        tr = QgsCoordinateTransform(lyr.crs(), proj.crs(), proj)
        e = tr.transformBoundingBox(lyr.extent())
        ext = e if ext is None else ext.combineExtentWith(e) or ext
    ext.grow(grow_m)
    return ext


def _nice_interval(span, target_lines=4):
    raw = span / target_lines
    for step in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0):
        if raw <= step:
            return step
    return 10.0


def _nice_scalebar_km(map_width_m):
    """2 segments spanning roughly a quarter of the map width, round numbers."""
    target = map_width_m / 4 / 2 / 1000
    for step in (1, 2, 5, 10, 20, 50, 100):
        if target <= step:
            return step
    return 200


def _north_arrow_svg():
    for d in QgsApplication.svgPaths():
        p = os.path.join(d, "arrows", "NorthArrow_02.svg")
        if os.path.exists(p):
            return p
    return None


def _sorted_maps(layout):
    return sorted(
        [i for i in layout.items() if isinstance(i, QgsLayoutItemMap)],
        key=lambda m: m.pagePos().x(),
    )


def _prune_legend(legend, keep_ids, resync=False):
    """Crash-safe legend pruning. NEVER setRootGroup(a Python-owned QgsLayerTree):
    QGIS does not take ownership and the GC'd tree dangles -> access violation.
    Prune the legend model's own root in place; hide (not rename) kept nodes."""
    if resync:
        legend.setAutoUpdateModel(True)
        legend.refresh()
    legend.setAutoUpdateModel(False)
    root = legend.model().rootGroup()
    for node in list(root.findLayers()):
        if node.layerId() not in keep_ids:
            root.removeChildNode(node)
        elif len(keep_ids) == 1:
            QgsLegendRenderer.setNodeLegendStyle(node, QgsLegendStyle.Hidden)
    legend.setResizeToContents(True)
    legend.refresh()
    legend.adjustBoxSize()


def _compact_legend_if_overflowing(legend, page_h=210):
    if legend.pagePos().y() + legend.rect().height() <= page_h - 4:
        return
    legend.setSymbolHeight(3.0)
    legend.setSymbolWidth(6.0)
    for comp in (QgsLegendStyle.Title, QgsLegendStyle.Group,
                 QgsLegendStyle.Subgroup, QgsLegendStyle.SymbolLabel):
        st = legend.style(comp)
        f = st.font()
        f.setPointSizeF(max(7.0, f.pointSizeF() - 2))
        st.setFont(f)
        legend.setStyle(comp, st)
    legend.refresh()
    legend.adjustBoxSize()


def _configure_scalebar(sb, main_map):
    sb.setLinkedMap(main_map)  # add-order trap: default links the first map item
    sb.applyDefaultSize()
    # applyDefaultSize resets to meters — km units MUST be set after it
    sb.setUnits(QgsUnitTypes.DistanceKilometers)
    sb.setUnitLabel("km")
    km = _nice_scalebar_km(main_map.extent().width())
    sb.setUnitsPerSegment(km)
    sb.setNumberOfSegments(2)
    sb.setNumberOfSegmentsLeft(0)
    sb.setHeight(2.2)
    tf = sb.textFormat()
    tf.setSize(7.5)
    sb.setTextFormat(tf)
    x, y, _, _ = GEOM["scalebar"]
    sb.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    sb.update()


def _configure_graticule(main_map):
    proj = _project()
    g = main_map.grid()
    g.setEnabled(True)
    g.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    tr = QgsCoordinateTransform(proj.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), proj)
    e4326 = tr.transformBoundingBox(main_map.extent())
    g.setIntervalX(_nice_interval(e4326.width()))
    g.setIntervalY(_nice_interval(e4326.height()))
    g.setStyle(QgsLayoutItemMapGrid.Solid)
    g.setGridLineWidth(0.15)
    g.setGridLineColor(QColor(120, 120, 120, 110))
    g.setAnnotationEnabled(True)
    g.setAnnotationPrecision(2)
    f = QFont()
    f.setPointSize(7)
    g.setAnnotationFont(f)
    g.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Right)
    g.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Top)


def _add_label(layout, text, font_size, geom_key):
    lab = QgsLayoutItemLabel(layout)
    lab.setText(text)
    f = QFont()
    f.setPointSize(font_size)
    lab.setFont(f)
    layout.addLayoutItem(lab)
    x, y, w, h = GEOM[geom_key]
    lab.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    lab.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    return lab


def create_standard_map_layout(
    name,
    layer_ids,
    title,
    footer,
    legend_title=None,
    inset_layer_ids=None,
    detail_extent=None,
    detail_note=None,
    graticule=True,
    north_arrow=True,
    scalebar=True,
    legend=True,
    inset=True,
    **kwargs,
):
    """Build the full standard report-map layout in one call.

    layer_ids: layers for the main view, drawing order top-first.
    inset_layer_ids: layers for the detail inset (defaults to layer_ids).
    detail_extent: [xmin, ymin, xmax, ymax] in project CRS; default = center 12x12 km.
    Returns layout name, scale, and item counts.
    """
    proj = _project()
    lm = proj.layoutManager()
    old = lm.layoutByName(name)
    if old is not None:
        lm.removeLayout(old)  # duplicate names invalidate the new Python object

    layout = QgsPrintLayout(proj)
    layout.initializeDefaults()
    layout.setName(name)
    if not lm.addLayout(layout):
        raise RuntimeError(f"Could not add layout {name}")

    main_layers = _layers(layer_ids)
    inset_layers = _layers(inset_layer_ids) if inset_layer_ids else main_layers

    # main map
    main = QgsLayoutItemMap(layout)
    layout.addLayoutItem(main)
    x, y, w, h = GEOM["main_map"]
    main.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    main.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    main.setLayers(main_layers)
    main.setKeepLayerSet(True)
    main.zoomToExtent(_union_extent_project_crs(main_layers))

    # detail inset + red footprint box on the main map
    if inset:
        im = QgsLayoutItemMap(layout)
        layout.addLayoutItem(im)
        x, y, w, h = GEOM["inset_map"]
        im.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        im.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
        im.setLayers(inset_layers)
        im.setKeepLayerSet(True)
        im.setFrameEnabled(True)
        if detail_extent is None:
            c = main.extent().center()
            detail_extent = [c.x() - 6000, c.y() - 6000, c.x() + 6000, c.y() + 6000]
        im.setExtent(QgsRectangle(*[float(v) for v in detail_extent]))
        ov = main.overview()
        ov.setEnabled(True)
        ov.setLinkedMap(im)
        ov.setFrameSymbol(QgsFillSymbol.createSimple(
            {"color": "255,0,0,0", "outline_color": "#e34948", "outline_width": "0.6"}))
        _add_label(layout, detail_note or "Detail (red box on main map)", 9, "inset_note")

    _add_label(layout, title, 14, "title")
    _add_label(layout, footer, 7, "footer")

    if graticule:
        _configure_graticule(main)

    if legend:
        leg = QgsLayoutItemLegend(layout)
        leg.setTitle(legend_title or "Legend")
        leg.setLinkedMap(main)
        layout.addLayoutItem(leg)
        x, y, w, h = GEOM["legend"]
        leg.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        keep = set(layer_ids) | set(inset_layer_ids or [])
        _prune_legend(leg, keep)
        _compact_legend_if_overflowing(leg)

    if scalebar:
        sb = QgsLayoutItemScaleBar(layout)
        sb.setStyle("Single Box")
        layout.addLayoutItem(sb)
        _configure_scalebar(sb, main)

    if north_arrow:
        svg = _north_arrow_svg()
        if svg:
            pic = QgsLayoutItemPicture(layout)
            pic.setPicturePath(svg)
            layout.addLayoutItem(pic)
            x, y, w, h = GEOM["north"]
            pic.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
            pic.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))

    main.refresh()
    return {
        "layout": name,
        "scale": int(main.scale()),
        "items": len(list(layout.items())),
        "detail_extent": detail_extent,
    }


def duplicate_map_layout(
    template_name,
    new_name,
    layer_ids,
    title,
    footer=None,
    legend_title=None,
    inset_layer_ids=None,
    detail_extent=None,
    detail_note=None,
    **kwargs,
):
    """Duplicate a verified standard layout for another variable and swap
    layers, title, footer, detail window and legend. Furniture stays identical."""
    proj = _project()
    lm = proj.layoutManager()
    tpl = lm.layoutByName(template_name)
    if tpl is None:
        raise ValueError(f"Template layout not found: {template_name}")
    old = lm.layoutByName(new_name)
    if old is not None:
        lm.removeLayout(old)
    layout = lm.duplicateLayout(tpl, new_name)
    if layout is None:
        raise RuntimeError("duplicateLayout failed")

    main_layers = _layers(layer_ids)
    inset_layers = _layers(inset_layer_ids) if inset_layer_ids else main_layers
    maps = _sorted_maps(layout)
    main = maps[0]
    main.setLayers(main_layers)
    main.setKeepLayerSet(True)
    if len(maps) > 1:
        im = maps[1]
        im.setLayers(inset_layers)
        im.setKeepLayerSet(True)
        if detail_extent:
            im.setExtent(QgsRectangle(*[float(v) for v in detail_extent]))

    labels = sorted(
        [i for i in layout.items() if isinstance(i, QgsLayoutItemLabel)],
        key=lambda lab: (lab.pagePos().y(), lab.pagePos().x()),
    )
    for lab in labels:
        f = lab.font().pointSize()
        if f >= 12:
            lab.setText(title)
        elif f <= 8 and footer:
            lab.setText(footer)
        elif 8 < f < 12 and detail_note:
            lab.setText(detail_note)
        lab.refresh()

    for leg in [i for i in layout.items() if isinstance(i, QgsLayoutItemLegend)]:
        if legend_title:
            leg.setTitle(legend_title)
        keep = set(layer_ids) | set(inset_layer_ids or [])
        _prune_legend(leg, keep, resync=True)
        _compact_legend_if_overflowing(leg)

    for m in maps:
        m.refresh()
    return {"layout": new_name, "scale": int(main.scale())}


def find_detail_window(layer_id, window_m=12000, grid=64, **kwargs):
    """Find the densest-valid-data window of a raster layer: the report's
    detail inset should show data, not nodata. Scans a decimated block for the
    window_m x window_m square with the highest valid fraction.
    Returns extent in PROJECT CRS."""
    proj = _project()
    lyr = proj.mapLayer(layer_id)
    if lyr is None:
        raise ValueError(f"Layer not found: {layer_id}")
    dp = lyr.dataProvider()
    ext = lyr.extent()
    nx = ny = 400
    blk = dp.block(1, ext, nx, ny)
    nd = dp.sourceNoDataValue(1)
    mx, my = _m_per_unit_xy(lyr.crs(), ext)
    win_x = max(2, round(window_m / (ext.width() * mx) * nx))
    win_y = max(2, round(window_m / (ext.height() * my) * ny))
    best, bi, bj = -1.0, 0, 0
    step_i = max(1, win_y // 4)
    step_j = max(1, win_x // 4)
    # integral-image-free scan on the coarse grid is fast enough at 400x400
    valid = [[0] * (nx + 1) for _ in range(ny + 1)]
    for i in range(ny):
        row = valid[i + 1]
        prev = valid[i]
        for j in range(nx):
            v = blk.value(i, j)
            ok = 1
            if v is None or (nd is not None and v == nd) or v != v or v == 0:
                ok = 0
            row[j + 1] = ok + prev[j + 1] + row[j] - prev[j]
    for i in range(0, ny - win_y, step_i):
        for j in range(0, nx - win_x, step_j):
            lo_row, hi_row = valid[i], valid[i + win_y]
            s = hi_row[j + win_x] - lo_row[j + win_x] - hi_row[j] + lo_row[j]
            f = s / (win_x * win_y)
            if f > best:
                best, bi, bj = f, i, j
    x0 = ext.xMinimum() + bj / nx * ext.width()
    y1 = ext.yMaximum() - bi / ny * ext.height()
    x1 = x0 + win_x / nx * ext.width()
    y0 = y1 - win_y / ny * ext.height()
    tr = QgsCoordinateTransform(lyr.crs(), proj.crs(), proj)
    e = tr.transformBoundingBox(QgsRectangle(x0, y0, x1, y1))
    return {"extent": [e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()],
            "valid_fraction": round(best, 3)}


def _m_per_unit_xy(crs, ext):
    """Meters per map unit along x and y — geographic degrees differ per axis."""
    if crs.mapUnits() == QgsUnitTypes.DistanceMeters:
        return 1.0, 1.0
    lat = math.radians(ext.center().y())
    return 111319.49 * math.cos(lat), 111132.95 - 559.85 * math.cos(2 * lat)


def apply_quantile_style(
    layer_id,
    classes=5,
    ramp="RdYlGn",
    class_names=None,
    decimals=0,
    min_valid=0.0,
    **kwargs,
):
    """Quantile N-class discrete style for a continuous raster, with clean
    'Very Low (< a)' ... 'Very High (> b)' labels. min_valid excludes a mask
    floor (e.g. 0 = non-crop) from the class breaks."""
    proj = _project()
    lyr = proj.mapLayer(layer_id)
    if lyr is None:
        raise ValueError(f"Layer not found: {layer_id}")
    dp = lyr.dataProvider()
    breaks = []
    for k in range(1, classes):
        _, hi = dp.cumulativeCut(1, min_valid, k / classes, lyr.extent(), 250000)
        breaks.append(round(hi, decimals) if decimals else round(hi))
    if class_names is None:
        class_names = (["Very Low", "Low", "Medium", "High", "Very High"]
                       if classes == 5 else
                       [f"Class {i + 1}" for i in range(classes)])
    fmt = f"%.{decimals}f" if decimals else "%d"
    labels = [f"{class_names[0]} (< {fmt % breaks[0]})"]
    labels += [f"{class_names[i]} ({fmt % breaks[i - 1]} - {fmt % breaks[i]})"
               for i in range(1, classes - 1)]
    labels += [f"{class_names[-1]} (> {fmt % breaks[-1]})"]
    r = QgsStyle.defaultStyle().colorRamp(ramp)
    fn = QgsColorRampShader(0, breaks[-1], r, QgsColorRampShader.Discrete)
    vals = [*breaks, 3.4e38]  # last discrete item must be a huge float, not inf
    items = [QgsColorRampShader.ColorRampItem(v, r.color(i / (classes - 1)), lab)
             for i, (v, lab) in enumerate(zip(vals, labels, strict=True))]
    fn.setColorRampItemList(items)
    rs = QgsRasterShader()
    rs.setRasterShaderFunction(fn)
    lyr.setRenderer(QgsSingleBandPseudoColorRenderer(dp, 1, rs))
    lyr.triggerRepaint()
    return {"layer": lyr.name(), "breaks": breaks, "labels": labels}


def apply_hillshade_context(dem_source, ramp="Viridis", z_factor=3.0, opacity=0.5,
                            layer_name="Elevation (m a.s.l.)", **kwargs):
    """Create the elevation+hillshade context pair from a DEM path: color relief
    (percentile-stretched, whole-number legend) + hillshade multiplied on top.
    Use both ids (hillshade first) as a standard layout's main-view layer_ids."""
    proj = _project()
    hs = QgsRasterLayer(dem_source, "Hillshade")
    if not hs.isValid():
        raise ValueError(f"Cannot open DEM: {dem_source}")
    r = QgsHillshadeRenderer(hs.dataProvider(), 1, 315, 45)
    r.setZFactor(z_factor)
    hs.setRenderer(r)
    hs.setBlendMode(QPainter.CompositionMode_Multiply)
    hs.renderer().setOpacity(opacity)
    proj.addMapLayer(hs)

    el = QgsRasterLayer(dem_source, layer_name)
    dp = el.dataProvider()
    lo, hi = dp.cumulativeCut(1, 0.01, 0.99, el.extent(), 250000)
    rr = QgsStyle.defaultStyle().colorRamp(ramp)
    fn = QgsColorRampShader(lo, hi, rr, QgsColorRampShader.Interpolated)
    fn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(lo + (hi - lo) * f, rr.color(f),
                                         "%.0f" % (lo + (hi - lo) * f))
        for f in (0, 0.25, 0.5, 0.75, 1.0)
    ])
    ls = QgsColorRampLegendNodeSettings()  # legend node settings live on the shader fn
    nf = QgsBasicNumericFormat()
    nf.setNumberDecimalPlaces(0)
    ls.setNumericFormat(nf)
    fn.setLegendSettings(ls)
    rs = QgsRasterShader()
    rs.setRasterShaderFunction(fn)
    el.setRenderer(QgsSingleBandPseudoColorRenderer(dp, 1, rs))
    proj.addMapLayer(el)
    return {"hillshade_id": hs.id(), "elevation_id": el.id(),
            "range": [round(lo), round(hi)],
            "main_view_layer_ids": [hs.id(), el.id()]}


def save_layout_template(layout_name, path, **kwargs):
    """Save a verified layout as a .qpt template for reuse across projects."""
    from qgis.core import QgsReadWriteContext
    lm = _project().layoutManager()
    layout = lm.layoutByName(layout_name)
    if layout is None:
        raise ValueError(f"Layout not found: {layout_name}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok = layout.saveAsTemplate(path, QgsReadWriteContext())
    if not ok:
        raise RuntimeError(f"saveAsTemplate failed for {path}")
    return {"saved": path}


HANDLERS = {
    "create_standard_map_layout": create_standard_map_layout,
    "duplicate_map_layout": duplicate_map_layout,
    "find_detail_window": find_detail_window,
    "apply_quantile_style": apply_quantile_style,
    "apply_hillshade_context": apply_hillshade_context,
    "save_layout_template": save_layout_template,
}
