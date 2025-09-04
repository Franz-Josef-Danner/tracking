# SPDX-License-Identifier: GPL-2.0-or-later
"""
Kaiserlich Tracker – Top-Level Add-on (__init__.py)
- Scene-Properties + UI-Panel + Coordinator-Launcher
- Der MODALE Operator kommt aus Operator/tracking_coordinator.py
"""
from __future__ import annotations
import bpy
from bpy.types import PropertyGroup, Panel, Operator as BpyOperator
from bpy.props import IntProperty, FloatProperty, CollectionProperty, BoolProperty, StringProperty
import math
import time
try:
    import gpu
    from gpu_extras.batch import batch_for_shader
except Exception:
    gpu = None

# WICHTIG: nur Klassen importieren, kein register() von Submodulen aufrufen
from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator
from .Helper.bidirectional_track import CLIP_OT_bidirectional_track

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Launcher + UI für den Kaiserlich Tracking-Workflow",
    "category": "Tracking",
}

# ---------------------------------------------------------------------------
# Scene-Properties
# ---------------------------------------------------------------------------
class RepeatEntry(PropertyGroup):
    frame: IntProperty(name="Frame", default=0, min=0)
    count: IntProperty(name="Count", default=0, min=0)

# --- Solve-Error Log Items ---
class KaiserlichSolveErrItem(PropertyGroup):
    attempt: IntProperty(name="Attempt", default=0, min=0)
    value:   FloatProperty(name="Avg Error", default=float("nan"))
    stamp:   StringProperty(name="Time", default="")

# --- UI-Redraw Helper (CLIP-Editor) ---
def _tag_clip_redraw() -> None:
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
        for win in wm.windows:
            scr = getattr(win, "screen", None)
            if not scr:
                continue
            for area in scr.areas:
                if area.type != "CLIP_EDITOR":
                    continue
                for region in area.regions:
                    if region.type in {"WINDOW", "UI"}:
                        region.tag_redraw()
    except Exception:
        pass

# Öffentliche Helper-Funktion (vom Coordinator aufrufbar)
def kaiserlich_solve_log_add(context: bpy.types.Context, value: float | None) -> None:
    """Logge einen Solve-Versuch NUR bei gültigem numerischen Wert (kein None/NaN/Inf)."""
    scn = context.scene if hasattr(context, "scene") else None
    if value is None:
        return
    try:
        v = float(value)
    except Exception:
        return
    if (v != v) or math.isinf(v):  # NaN oder ±Inf
        return
    scn = context.scene
    try:
        scn.kaiserlich_solve_attempts += 1
    except Exception:
        scn["kaiserlich_solve_attempts"] = int(scn.get("kaiserlich_solve_attempts", 0)) + 1
    item = scn.kaiserlich_solve_err_log.add()
    item.attempt = int(scn.kaiserlich_solve_attempts)
    item.value   = v
    item.stamp   = time.strftime("%H:%M:%S")
    try:
        coll = scn.kaiserlich_solve_err_log
        coll.move(len(coll) - 1, 0)
        scn.kaiserlich_solve_err_idx = 0
    except Exception:
        pass
    coll = scn.kaiserlich_solve_err_log
    while len(coll) > 10:
        coll.remove(len(coll) - 1)
    _tag_clip_redraw()
    
# GPU-Overlay (Sparkline) – Draw Handler
_solve_graph_handle = None
def _draw_solve_graph():
    if gpu is None:
        return
    import blf
    import math as _m
    scn = getattr(bpy.context, "scene", None)

    def _blf_size(fid: int, sz: int) -> None:
        try:
            blf.size(fid, sz)
        except TypeError:
            try:
                blf.size(fid, sz, 72)
            except Exception:
                pass

    if not scn or not getattr(scn, "kaiserlich_solve_graph_enabled", False):
        return
    coll = getattr(scn, "kaiserlich_solve_err_log", [])
    seq = sorted((it.attempt, it.value) for it in coll if it.value == it.value)
    has_data = bool(seq)
    try:
        _vx, _vy, W, H = gpu.state.viewport_get()
    except Exception:
        region = getattr(bpy.context, "region", None)
        if not region:
            return
        W, H = region.width, region.height
    pad = 16
    gw, gh = min(320, W - 2*pad), 80
    yaxis_w = 42
    ox, oy = W - gw - pad, pad
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    box = [(ox, oy), (ox+gw, oy), (ox+gw, oy+gh), (ox, oy+gh)]
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.35)); batch.draw(shader)

    def _draw_title():
        title = "Average Trend"
        font_id = 0
        try:
            _blf_size(font_id, 12)
            tw, th = blf.dimensions(font_id, title)
            tx = ox + yaxis_w
            ty = oy + gh + 6
            ty = min(ty, H - th - 2)
            tx = max(tx, 0)
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, tx, ty, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, title)
            blf.disable(font_id, blf.SHADOW)
        except Exception:
            pass

    if not has_data:
        try:
            _draw_title()
            font_id = 0
            _blf_size(font_id, 11)
            txt = "No data yet"
            tw, th = blf.dimensions(font_id, txt)
            cx = ox + yaxis_w + (gw - yaxis_w - tw) * 0.5
            cy = oy + (gh - th) * 0.5
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, cx, cy, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, txt)
            blf.disable(font_id, blf.SHADOW)
        except Exception:
            pass
        return

    vals = [v for _, v in seq]
    avg_vals = []
    s = 0.0
    for i, v in enumerate(vals, 1):
        s += float(v)
        avg_vals.append(s / i)
    take_vals = avg_vals[-10:]
    vmin, vmax = (min(take_vals), max(take_vals)) if take_vals else (0.0, 1.0)
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-12
    n = len(take_vals)
    ln = max(1, n - 1)
    coords = []
    for i, val in enumerate(take_vals):
        x = ox + yaxis_w + (i / ln) * (gw - yaxis_w)
        y = oy + ((val - vmin) / (vmax - vmin)) * gh
        coords.append((x, y))
    try:
        step = 5.0
        tick0 = _m.ceil (vmin / step) * step
        tickN = _m.floor(vmax / step) * step
        ticks = []
        if tickN >= tick0:
            count = int(_m.floor((tickN - tick0) / step)) + 1
            count = min(count, 64)
            ticks = [tick0 + i * step for i in range(count)]
        yaxis_x = ox + yaxis_w
        batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, oy), (yaxis_x, oy+gh)]})
        shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.5)); batch.draw(shader)
        font_id = 0; _blf_size(font_id, 11)
        prec = 0
        _fmt = f"{{:.{prec}f}}"
        for tv in ticks:
            rel = (tv - vmin) / (vmax - vmin)
            y = oy + rel * gh
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x-6, y), (yaxis_x, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.8)); batch.draw(shader)
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, y), (ox+gw, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.15)); batch.draw(shader)
            lbl = _fmt.format(tv)
            lx = ox + 4
            ly = y - 6
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, lx, ly, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, lbl)
            blf.disable(font_id, blf.SHADOW)
    except Exception:
        pass
    if len(coords) == 1:
        coords.append((coords[0][0] + 1, coords[0][1]))
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    _reset_width = False
    try:
        gpu.state.line_width_set(2.0)
        _reset_width = True
    except Exception:
        pass
    try:
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
        batch.draw(shader)
    except Exception:
        pass
    _draw_title()
    if _reset_width:
        try: gpu.state.line_width_set(1.0)
        except Exception: pass

# ---------------------------------------------------------------------------
# … Rest (Register/Unregister, Panel, etc.) bleibt unverändert …
# ---------------------------------------------------------------------------
