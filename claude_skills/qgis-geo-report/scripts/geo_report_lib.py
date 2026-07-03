"""Reusable WSL-side helpers for qgis-geo-report analyses.

Usage: copy this file into the report's codes/ folder (keeps the report
self-contained and reproducible), then `from geo_report_lib import *`.
Everything is data-agnostic; nothing here knows about crops or basins.
"""
import math
import numpy as np
from osgeo import gdal

gdal.UseExceptions()

# ---------------------------------------------------------------- raster IO
# numpy-2 safe: ReadRaster + frombuffer, never gdal_array (often built vs numpy 1.x)
_GDT = {"Byte": np.uint8, "UInt16": np.uint16, "Int16": np.int16, "UInt32": np.uint32,
        "Int32": np.int32, "Float32": np.float32, "Float64": np.float64}


def read_raster(path, band=1, out_shape=None, nodata_to_nan=True):
    """Read a raster band as float ndarray. out_shape=(ny, nx) decimates via GDAL.
    Returns (array, geotransform)."""
    ds = gdal.Open(path)
    b = ds.GetRasterBand(band)
    ny, nx = out_shape if out_shape else (ds.RasterYSize, ds.RasterXSize)
    dt = _GDT[gdal.GetDataTypeName(b.DataType)]
    buf = b.ReadRaster(0, 0, ds.RasterXSize, ds.RasterYSize, nx, ny,
                       gdal.GetDataTypeByName(gdal.GetDataTypeName(b.DataType)))
    a = np.frombuffer(buf, dtype=dt).reshape(ny, nx).astype(float)
    if nodata_to_nan:
        nd = b.GetNoDataValue()
        if nd is not None and not math.isnan(nd):
            a[a == nd] = np.nan
    return a, ds.GetGeoTransform()


def chunked_hist(path, band=1, valid=(0.5, 30000), bin_width=0.25, vmax=None, rows=1000):
    """Full-resolution histogram of a large raster without loading it whole.
    Returns (bin_edges, counts). Median: edges[np.searchsorted(counts.cumsum(), n/2)]."""
    ds = gdal.Open(path)
    b = ds.GetRasterBand(band)
    nx, ny = ds.RasterXSize, ds.RasterYSize
    dt = _GDT[gdal.GetDataTypeName(b.DataType)]
    if vmax is None:
        vmax = b.GetStatistics(0, 1)[1]
    edges = np.arange(0, vmax + bin_width, bin_width)
    hist = np.zeros(len(edges) - 1, dtype=np.int64)
    for y0 in range(0, ny, rows):
        h = min(rows, ny - y0)
        a = np.frombuffer(b.ReadRaster(0, y0, nx, h), dtype=dt).astype(float)
        v = a[(a > valid[0]) & (a < valid[1])]
        hist += np.histogram(v, bins=edges)[0]
    return edges, hist


# ---------------------------------------------------------------- geometry
def ha_per_deg2(mid_lat):
    """Hectares per square degree at a latitude. Use for EPSG:4326 zonal 'deg2'
    columns — geographic pixel COUNTS are not areas (pixels shrink with latitude)."""
    m_lon = 111319.49 * math.cos(math.radians(mid_lat))
    m_lat = 111132.95 - 559.85 * math.cos(2 * math.radians(mid_lat))
    return m_lon * m_lat / 1e4


# ---------------------------------------------------------------- statistics
def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def profile(values):
    q = np.percentile(values, [5, 25, 50, 75, 95])
    return {"n": int(values.size), "mean": float(values.mean()), "sd": float(values.std()),
            "p5": q[0], "q1": q[1], "median": q[2], "q3": q[3], "p95": q[4],
            "min": float(values.min()), "max": float(values.max())}


def by_bins(y, ym, driver, inner_edges, labels, dm=None, min_n=200):
    """Conditional stats of response y in bins of a continuous driver.
    inner_edges: the bin boundaries between len(labels) bins."""
    out = []
    m0 = ym if dm is None else (ym & dm)
    idx = np.digitize(driver, inner_edges)
    for i, lab in enumerate(labels):
        m = m0 & (idx == i)
        n = int(m.sum())
        rec = {"bin": lab, "n": n, "reliable": n >= min_n}
        if n >= min_n:
            v = y[m]
            q = np.percentile(v, [25, 50, 75])
            rec.update(mean=float(v.mean()), q1=q[0], median=q[1], q3=q[2])
        out.append(rec)
    return out


def by_class(y, ym, classes, mapping, cell_ha=None, min_n=200):
    """Conditional stats of y per integer class. ROUND float-coded classes first
    (np.round) — categorical rasters often store 1.00002-style values."""
    out = []
    for k, lab in mapping.items():
        m = ym & (classes == k)
        n = int(m.sum())
        rec = {"class": lab, "n": n, "reliable": n >= min_n}
        if cell_ha:
            rec["area_ha"] = float((classes == k).sum() * cell_ha)
        if n >= min_n:
            v = y[m]
            q = np.percentile(v, [25, 50, 75])
            rec.update(mean=float(v.mean()), q1=q[0], median=q[1], q3=q[2])
        out.append(rec)
    return out


REL_BANDS = [0.6, 0.8, 1.0, 1.2]
REL_LABELS = ["<60%", "60-80%", "80-100%", "100-120%", ">120%"]


def relative_bands(edges, hist, px_area_ha):
    """Area per band of value relative to the distribution's own median — the
    scale-free way to compare responses with different magnitudes."""
    cum = np.cumsum(hist)
    med = edges[np.searchsorted(cum, cum[-1] / 2)]
    idx = np.digitize(edges[:-1] + np.diff(edges) / 2, [med * f for f in REL_BANDS])
    bands = {}
    for i, lab in enumerate(REL_LABELS):
        n = int(hist[idx == i].sum())
        bands[lab] = {"area_ha": n * px_area_ha, "share": n / cum[-1]}
    return float(med), bands


# ---------------------------------------------------------------- chart style
# Reference dataviz palette (light surface). Categorical slots in fixed order.
SURF, INK, INK2, MUT, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948"]
SEQ = "#256abf"                       # single-series bars
SEQ_CMAPS = ["Blues", "Greens", "Oranges", "Purples"]   # hexbin ramp per response


def apply_chart_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 10,
        "text.color": INK, "axes.edgecolor": BASE, "axes.labelcolor": INK2,
        "xtick.color": MUT, "ytick.color": MUT, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6,
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    })
    return plt


def style_ax(ax, value_axis="x"):
    """Recessive axes: grid only along the value axis, no ticks, no top/right/left spines."""
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.grid(axis=value_axis)
    ax.grid(False, axis="y" if value_axis == "x" else "x")
    ax.tick_params(length=0)


def save_fig(fig, figures_dir, name):
    fig.savefig(f"{figures_dir}/{name}.png", dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)


def hexbin_gallery(plt, responses, drivers, figures_dir, name="chart_scatter_gallery",
                   units=""):
    """The relationship gallery: responses × drivers hexbin grid, decile-binned
    median overlay, Spearman ρ + n per panel. A flat cloud is a finding — ship it.
    responses: list of (label, y_array, valid_mask, ylim); drivers: list of
    (label, x_array, valid_mask, xlim-or-None)."""
    nr, nc = len(responses), len(drivers)
    fig, axes = plt.subplots(nr, nc, figsize=(3.1 * nc + 0.6, 3.0 * nr + 0.4), squeeze=False)
    for i, (rlab, y, vm, ylim) in enumerate(responses):
        cmap = SEQ_CMAPS[i % len(SEQ_CMAPS)]
        for j, (dlab, d, dm, xlim) in enumerate(drivers):
            ax = axes[i][j]
            m = vm & dm
            xv, yv = d[m], y[m]
            if xlim:
                keep = (xv >= xlim[0]) & (xv <= xlim[1])
                xv, yv = xv[keep], yv[keep]
            ax.hexbin(xv, yv, gridsize=42, cmap=cmap, mincnt=1, linewidths=0.1)
            edges = np.unique(np.percentile(xv, np.arange(0, 101, 10)))
            mids, meds = [], []
            for k in range(len(edges) - 1):
                mm = (xv >= edges[k]) & (xv < edges[k + 1])
                if mm.sum() > 100:
                    mids.append(xv[mm].mean()); meds.append(np.median(yv[mm]))
            ax.plot(mids, meds, "-o", color=INK, lw=1.6, ms=3.5, zorder=5)
            ax.text(0.03, 0.95, f"ρ = {spearman(xv, yv):+.2f}\nn = {len(xv):,}",
                    transform=ax.transAxes, va="top", fontsize=8, color=INK2,
                    bbox=dict(fc=SURF, ec="none", alpha=0.75, pad=1.5))
            ax.set_ylim(*ylim)
            if xlim: ax.set_xlim(*xlim)
            for s in ["top", "right"]:
                ax.spines[s].set_visible(False)
            ax.tick_params(length=0)
            ax.grid(True, color=GRID, lw=0.5, alpha=0.7)
            ax.set_xlabel(dlab) if i == nr - 1 else ax.set_xticklabels([])
            if j == 0: ax.set_ylabel(f"{rlab}\n{units}")
            else: ax.set_yticklabels([])
    fig.subplots_adjust(hspace=0.12, wspace=0.08)
    save_fig(fig, figures_dir, name)


def grouped_barh(plt, categories, series, figures_dir, name, xlabel,
                 annotate=None, iqr=None):
    """Horizontal grouped bars for ≤3 series over shared categories (already sorted).
    series: list of (label, {cat: value}); iqr: optional (label→{cat:(q1,q3)});
    annotate: fn(label, cat, value) → bar-end text."""
    y = np.arange(len(categories))
    h = 0.76 / len(series)
    fig, ax = plt.subplots(figsize=(7.6, 0.5 * len(categories) + 1.2))
    for si, (lab, vals) in enumerate(series):
        off = (len(series) - 1) / 2 * h - si * h
        v = [vals[c] for c in categories]
        ax.barh(y + off, v, height=h * 0.92, color=SERIES[si], label=lab, zorder=3)
        if iqr:
            q = [iqr[lab][c] for c in categories]
            ax.hlines(y + off, [a for a, _ in q], [b for _, b in q],
                      color=INK, lw=1.0, alpha=0.45, zorder=4)
        for yi, cat, val in zip(y + off, categories, v):
            txt = annotate(lab, cat, val) if annotate else f"{val:.0f}"
            ax.text(val + 0.01 * ax.get_xlim()[1], yi, txt, va="center",
                    fontsize=7.8, color=INK2, zorder=5)
    ax.set_yticks(y, categories, color=INK2)
    ax.set_xlabel(xlabel)
    style_ax(ax)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    save_fig(fig, figures_dir, name)
