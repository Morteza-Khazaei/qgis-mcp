"""Roadmap Tier-1/2 tools: discovery, edit safety, style introspection,
layout templates, async processing tasks.

Handler-style plain functions (kwargs in, JSON-serializable dict out),
registered into the dispatch table like report_layouts.HANDLERS.
Runs inside QGIS's bundled Python — keep the code Python-3.9 compatible.
"""
import contextlib
import fnmatch
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsPrintLayout,
    QgsProcessingAlgRunnerTask,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsReadWriteContext,
)
from qgis.PyQt.QtXml import QDomDocument


def _cpp_owned(obj):
    """Strip Python-side ownership from a QGIS-managed object (QGIS 4.2's
    bindings return layout wrappers that wrongly own the C++ object; a GC'd
    wrapper then deletes the real layout and later access crashes QGIS).
    Safe no-op on QGIS 3."""
    if obj is not None:
        try:
            from qgis.PyQt import sip
            sip.transferto(obj, None)
        except Exception:
            pass
    return obj


def _project():
    return QgsProject.instance()


def _get_layer(layer_id):
    lyr = _project().mapLayer(layer_id)
    if lyr is None:
        raise ValueError(f"Layer not found: {layer_id}")
    return lyr


# ── Discovery ───────────────────────────────────────────────────────────────


def list_files(path, pattern="*", max_entries=200, **kwargs):
    """Read-only directory listing so shell-less MCP clients (e.g. Claude
    Desktop) can discover data files to load. Returns name/type/size/mtime,
    directories first, geodata-relevant ordering left to the client."""
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if not p.exists():
        raise ValueError(f"Path does not exist: {p}")
    if p.is_file():
        st = p.stat()
        return {"path": str(p), "entries": [{
            "name": p.name, "type": "file", "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        }], "truncated": False}
    entries = []
    truncated = False
    dirs, files = [], []
    for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
        (dirs if child.is_dir() else files).append(child)
    for child in dirs + files:
        if not child.is_dir() and not fnmatch.fnmatch(child.name, pattern):
            continue
        if len(entries) >= max_entries:
            truncated = True
            break
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": None if child.is_dir() else st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            continue
    return {"path": str(p), "entries": entries, "truncated": truncated}


# ── Edit sessions ───────────────────────────────────────────────────────────


def begin_edits(layer_id, **kwargs):
    """Start an edit session: subsequent feature edits go to the layer's edit
    buffer and can be rolled back — without this they commit immediately."""
    lyr = _get_layer(layer_id)
    if lyr.isEditable():
        return {"editing": True, "note": "already in an edit session"}
    if not lyr.startEditing():
        raise RuntimeError(f"Could not start editing on {lyr.name()}")
    return {"editing": True, "layer": lyr.name()}


def commit_edits(layer_id, **kwargs):
    lyr = _get_layer(layer_id)
    if not lyr.isEditable():
        return {"committed": False, "note": "layer is not in an edit session"}
    if not lyr.commitChanges():
        errors = list(lyr.commitErrors())
        lyr.rollBack()
        raise RuntimeError("Commit failed (rolled back): {}".format("; ".join(errors)))
    return {"committed": True, "layer": lyr.name()}


def rollback_edits(layer_id, **kwargs):
    lyr = _get_layer(layer_id)
    if not lyr.isEditable():
        return {"rolled_back": False, "note": "layer is not in an edit session"}
    lyr.rollBack()
    return {"rolled_back": True, "layer": lyr.name()}


# ── Style introspection ─────────────────────────────────────────────────────


def _color_hex(color):
    try:
        return color.name()
    except Exception:
        return None


def _symbol_info(symbol):
    if symbol is None:
        return None
    info = {"color": _color_hex(symbol.color())}
    with contextlib.suppress(Exception):
        info["opacity"] = symbol.opacity()
    return info


def get_layer_style(layer_id, **kwargs):
    """Structured read of the current symbology — the counterpart of
    set_layer_style, so an AI can adjust an existing style instead of
    replacing it blind."""
    lyr = _get_layer(layer_id)
    r = lyr.renderer() if hasattr(lyr, "renderer") else None
    out = {"layer": lyr.name(), "layer_type": "raster", "renderer": None}

    if hasattr(lyr, "fields"):  # vector
        out["layer_type"] = "vector"
        if r is None:
            return out
        out["renderer"] = type(r).__name__
        with contextlib.suppress(Exception):
            out["opacity"] = lyr.opacity()
        rtype = r.type()
        if rtype == "singleSymbol":
            out["symbol"] = _symbol_info(r.symbol())
        elif rtype == "categorizedSymbol":
            out["field"] = r.classAttribute()
            out["categories"] = [
                {"value": c.value(), "label": c.label(), "symbol": _symbol_info(c.symbol())}
                for c in r.categories()
            ]
        elif rtype == "graduatedSymbol":
            out["field"] = r.classAttribute()
            out["ranges"] = [
                {"lower": rr.lowerValue(), "upper": rr.upperValue(),
                 "label": rr.label(), "symbol": _symbol_info(rr.symbol())}
                for rr in r.ranges()
            ]
        with contextlib.suppress(Exception):
            out["labeling_enabled"] = bool(lyr.labelsEnabled())
        return out

    # raster
    if r is None:
        return out
    out["renderer"] = type(r).__name__
    with contextlib.suppress(Exception):
        out["band"] = r.band()
    with contextlib.suppress(Exception):
        out["opacity"] = r.opacity()
    # pseudocolor: expose the class breaks the way apply_quantile_style writes them
    with contextlib.suppress(Exception):
        shader_fn = r.shader().rasterShaderFunction()
        out["classes"] = [
            {"value": it.value, "label": it.label, "color": _color_hex(it.color)}
            for it in shader_fn.colorRampItemList()
        ]
    with contextlib.suppress(Exception):  # paletted classes
        out["classes"] = [
            {"value": c.value, "label": c.label, "color": _color_hex(c.color)}
            for c in r.classes()
        ]
    return out


# ── Layout templates ────────────────────────────────────────────────────────


def load_layout_template(path, name, replacements=None, **kwargs):
    """Instantiate a saved .qpt template as a new print layout, optionally
    substituting literal text placeholders (e.g. {"{{title}}": "My map"}).
    Completes the loop with save_layout_template."""
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if not p.is_file():
        raise ValueError(f"Template not found: {p}")
    text = p.read_text(encoding="utf-8")
    for old, new in (replacements or {}).items():
        # XML-escape the replacement: templates are XML documents.
        esc = (str(new).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        text = text.replace(str(old), esc)
    doc = QDomDocument()
    res = doc.setContent(text)  # tuple (ok, msg, line, col) or plain bool per binding
    ok = res[0] if isinstance(res, tuple) else bool(res)
    if not ok:
        raise ValueError("Template XML did not parse")
    proj = _project()
    lm = proj.layoutManager()
    old_layout = lm.layoutByName(name)
    if old_layout is not None:
        lm.removeLayout(old_layout)
    layout = QgsPrintLayout(proj)
    # loadFromTemplate's return list undercounts on some bindings — count the
    # layout's real items instead.
    layout.loadFromTemplate(doc, QgsReadWriteContext())
    layout.setName(name)
    if not lm.addLayout(layout):
        raise RuntimeError(f"Could not add layout {name}")
    _cpp_owned(layout)
    return {"layout": name, "items_loaded": len(list(layout.items()))}


# ── Async processing tasks ──────────────────────────────────────────────────

_TASKS = {}


class _CapturingFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.lines = deque(maxlen=50)

    def pushInfo(self, info):
        self.lines.append(str(info))
        super().pushInfo(info)

    def reportError(self, error, fatalError=False):
        self.lines.append(f"ERROR: {error}")
        super().reportError(error, fatalError)


def start_processing_task(algorithm, parameters, **kwargs):
    """Run a Processing algorithm as a background QgsTask — for jobs that
    outlive the synchronous execute_processing timeout. Poll with task_status;
    result layers are added to the project on success."""
    alg = QgsApplication.processingRegistry().algorithmById(algorithm)
    if alg is None:
        raise ValueError(f"Unknown algorithm id: {algorithm}")
    context = QgsProcessingContext()
    context.setProject(_project())
    feedback = _CapturingFeedback()
    task = QgsProcessingAlgRunnerTask(alg, dict(parameters), context, feedback)
    task_id = uuid.uuid4().hex[:12]
    rec = {"task": task, "context": context, "feedback": feedback,
           "status": "running", "results": None, "algorithm": algorithm}
    _TASKS[task_id] = rec

    def _on_executed(successful, results):
        rec["status"] = "success" if successful else "failed"
        if successful:
            added = []
            store = context.temporaryLayerStore()
            for lyr in list(store.mapLayers().values()):
                store.takeMapLayer(lyr)
                _project().addMapLayer(lyr)
                added.append(lyr.id())
            rec["results"] = {"outputs": {k: str(v) for k, v in dict(results).items()},
                              "layers_added": added}

    task.executed.connect(_on_executed)
    QgsApplication.taskManager().addTask(task)
    return {"task_id": task_id, "algorithm": algorithm, "status": "running"}


def task_status(task_id, **kwargs):
    rec = _TASKS.get(task_id)
    if rec is None:
        raise ValueError(f"Unknown task id: {task_id}")
    status = rec["status"]
    out = {"task_id": task_id, "algorithm": rec["algorithm"], "status": status,
           "log_tail": list(rec["feedback"].lines)[-5:]}
    if status == "running":
        # The task manager DELETES the C++ task object once it finishes —
        # touch it only while running, and survive the race where it died
        # between our callback and this poll.
        try:
            out["progress"] = round(rec["task"].progress(), 1)
        except RuntimeError:
            out["progress"] = None
    else:
        out["progress"] = 100.0 if status == "success" else None
    if rec["results"] is not None:
        out["results"] = rec["results"]
    return out


def cancel_task(task_id, **kwargs):
    rec = _TASKS.get(task_id)
    if rec is None:
        raise ValueError(f"Unknown task id: {task_id}")
    try:
        rec["task"].cancel()
    except RuntimeError:
        return {"task_id": task_id, "status": rec["status"],
                "note": "task already finished"}
    rec["status"] = "canceled"
    return {"task_id": task_id, "status": "canceled"}


HANDLERS = {
    "list_files": list_files,
    "begin_edits": begin_edits,
    "commit_edits": commit_edits,
    "rollback_edits": rollback_edits,
    "get_layer_style": get_layer_style,
    "load_layout_template": load_layout_template,
    "start_processing_task": start_processing_task,
    "task_status": task_status,
    "cancel_task": cancel_task,
}
