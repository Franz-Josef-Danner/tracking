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
    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False)) if scn else False
    if dbg:
        pass  # removed print
    # Nur numerische Endwerte zulassen
    if value is None:
        if dbg:
            pass  # removed print
        return
    try:
        v = float(value)
    except Exception:
        if dbg:
            pass  # removed print
        return
    if (v != v) or math.isinf(v):  # NaN oder ±Inf
        if dbg:
            reason = "NaN" if (v != v) else "Inf"
            pass  # removed print
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
    # Neuester Eintrag ganz nach oben (Index 0)
    try:
        coll = scn.kaiserlich_solve_err_log
        coll.move(len(coll) - 1, 0)
        scn.kaiserlich_solve_err_idx = 0
    except Exception:
        pass
    # Ältere Werte abschneiden, nur die letzten 10 behalten
    coll = scn.kaiserlich_solve_err_log
    if dbg:
        pass  # removed print

    while len(coll) > 10:
        coll.remove(len(coll) - 1)
    if dbg:
        seq_dbg = [(it.attempt, it.value) for it in coll]
        pass  # removed print
    # UI-Refresh (CLIP-Editor + Sidebar)
    _tag_clip_redraw()
    
# GPU-Overlay (Sparkline) – Draw Handler
_solve_graph_handle = None
def _draw_solve_graph():
    if gpu is None:
        return
    import blf
    import math as _m
    scn = getattr(bpy.context, "scene", None)

    # --- BLF Compatibility: Blender 4.4 nutzt blf.size(font_id, size).
    # Ältere Versionen akzeptieren blf.size(font_id, size, dpi).
    def _blf_size(fid: int, sz: int) -> None:
        try:
            blf.size(fid, sz)             # Blender ≥ 4.4
        except TypeError:
            try:
                blf.size(fid, sz, 72)     # Fallback für ältere Versionen
            except Exception:
                pass

    if not scn or not getattr(scn, "kaiserlich_solve_graph_enabled", False):
        return
    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False))
    if dbg:
        pass  # removed print
    coll = getattr(scn, "kaiserlich_solve_err_log", [])
    # Chronologisch (ältester→neuester), NaN ignorieren
    seq = sorted((it.attempt, it.value) for it in coll if it.value == it.value)
    has_data = bool(seq)
    if dbg:
        pass  # removed print
    # Viewport-Maße robust beschaffen (Region ist nicht garantiert gesetzt)
    try:
        _vx, _vy, W, H = gpu.state.viewport_get()
    except Exception:
        region = getattr(bpy.context, "region", None)
        if not region:
            return
        W, H = region.width, region.height
    if dbg:
        pass  # removed print
    pad = 16
    gw, gh = min(320, W - 2*pad), 80
    # Platz links für Y-Achse reservieren (Achse + Labels)
    yaxis_w = 42
    ox, oy = W - gw - pad, pad
    if dbg:
        pass  # removed print
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    # Rahmen
    box = [(ox, oy), (ox+gw, oy), (ox+gw, oy+gh), (ox, oy+gh)]
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.35)); batch.draw(shader)
    # --- Titel-Helper: ÜBER der Box (links), mit BLF-Shadow ---
    def _draw_title():
        title = "Average Trend"
        font_id = 0
        try:
            _blf_size(font_id, 12)
            tw, th = blf.dimensions(font_id, title)
            # Position: oberhalb der Box, linksbündig an der Y-Achse
            tx = ox + yaxis_w
            ty = oy + gh + 6
            # Clipping-Schutz (nicht oberhalb des Viewports rauszeichnen)
            ty = min(ty, H - th - 2)
            tx = max(tx, 0)
            # Shadow/Outline für Lesbarkeit
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)       # weich, schwarz
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, tx, ty, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, title)
            blf.disable(font_id, blf.SHADOW)
            if dbg:
                pass  # removed print
        except Exception as ex:
            if dbg:
                pass  # removed print
    # Wenn keine Daten vorliegen: Hinweis zeichnen und früh aussteigen
    if not has_data:
        try:
            # Titel trotzdem zeigen (oben links in der Box)
            _draw_title()
            font_id = 0
            _blf_size(font_id, 11)
            txt = "No data yet"
            tw, th = blf.dimensions(font_id, txt)
            cx = ox + yaxis_w + (gw - yaxis_w - tw) * 0.5
            cy = oy + (gh - th) * 0.5
            # Shadow für Lesbarkeit
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

    # --- Gleitender kumulativer Durchschnitt für das Overlay ---
    vals = [v for _, v in seq]
    avg_vals = []
    s = 0.0
    for i, v in enumerate(vals, 1):
        s += float(v)
        avg_vals.append(s / i)
    # Nur die letzten 10 Punkte (chronologisch) – mit Durchschnittswerten
    take_vals = avg_vals[-10:]
    # Skala ausschließlich aus den letzten 10 Werten ableiten
    vmin, vmax = (min(take_vals), max(take_vals)) if take_vals else (0.0, 1.0)
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-12
    if dbg:
        pass  # removed print
        pass  # removed print
    n = len(take_vals)
    ln = max(1, n - 1)  # vermeidet Div/0, erlaubt 1-Punkt-Stub
    coords = []
    for i, val in enumerate(take_vals):
        x = ox + yaxis_w + (i / ln) * (gw - yaxis_w)
        y = oy + ((val - vmin) / (vmax - vmin)) * gh
        coords.append((x, y))
    if dbg:
        pass  # removed print
    # Y-Achse mit Ticks + numerischen Labels (links)
    try:
        # Feste Schrittweite: 5er-Sprünge
        step = 5.0
        # Ticks strikt im sichtbaren Datenbereich halten
        tick0 = _m.ceil (vmin / step) * step  # erster Tick >= vmin
        tickN = _m.floor(vmax / step) * step  # letzter Tick <= vmax
        ticks = []
        if tickN >= tick0:
            count = int(_m.floor((tickN - tick0) / step)) + 1
            count = min(count, 64)
            ticks = [tick0 + i * step for i in range(count)]
        if dbg:
            pass  # removed print
            pass  # removed print
        # Achsenlinie
        yaxis_x = ox + yaxis_w
        batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, oy), (yaxis_x, oy+gh)]})
        shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.5)); batch.draw(shader)
        # Ticks + Labels + horizontale Gridlines
        font_id = 0; _blf_size(font_id, 11)
        # 5er-Sprünge → ganzzahlige Labels
        prec = 0
        _fmt = f"{{:.{prec}f}}"
        for tv in ticks:
            rel = (tv - vmin) / (vmax - vmin)
            y = oy + rel * gh
            # Tick
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x-6, y), (yaxis_x, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.8)); batch.draw(shader)
            # Gridline dezent
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, y), (ox+gw, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.15)); batch.draw(shader)
            # Label
            lbl = _fmt.format(tv)
            lx = ox + 4
            ly = y - 6
            # Shadow/Outline für Lesbarkeit
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, lx, ly, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, lbl)
            blf.disable(font_id, blf.SHADOW)
        if dbg and ticks:
            y0 = oy + ((ticks[0]-vmin)/(vmax-vmin))*gh - 6
            y1 = oy + ((ticks[-1]-vmin)/(vmax-vmin))*gh - 6
            pass  # removed print
            pass  # removed print
    except Exception:
        pass
    # Kurve
    # Bei nur einem Punkt einen 1px-Stub zeichnen, damit sichtbar
    if len(coords) == 1:
        coords.append((coords[0][0] + 1, coords[0][1]))
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    # Sichtbarkeit verbessern: 2px Linienbreite (sofern verfügbar)
    _reset_width = False
    try:
        gpu.state.line_width_set(2.0)
        _reset_width = True
    except Exception:
        pass
    # >>> FEHLENDER DRAW-CALL (fix) <<<
    try:
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
        batch.draw(shader)
    except Exception:
        pass
    # Titel zuletzt zeichnen (oberste Ebene, nicht überdeckt)
    _draw_title()
    # Abschluss-Log sauber außerhalb des try/except-Blocks
    if dbg:
        pass  # removed print
    # Linienstärke zurücksetzen
    if _reset_width:
        try: gpu.state.line_width_set(1.0)
        except Exception: pass

def _register_scene_props() -> None:
    sc = bpy.types.Scene
    if not hasattr(sc, "repeat_frame"):
        sc.repeat_frame = CollectionProperty(type=RepeatEntry)
    if not hasattr(sc, "marker_frame"):
        sc.marker_frame = IntProperty(
            name="Marker per Frame", default=25, min=10, max=50,
            description="Mindestanzahl Marker pro Frame",
        )
    if not hasattr(sc, "frames_track"):
        sc.frames_track = IntProperty(
            name="Frames per Track", default=25, min=5, max=100,
            description="Track-Länge in Frames",
        )
    if not hasattr(sc, "error_track"):
        sc.error_track = FloatProperty(
            name="Error-Limit (px)", default=2.0, min=0.1, max=10.0,
            description="Maximal tolerierte Reprojektion (Pixel)",
        )
    # Solve-Log Properties
    if not hasattr(sc, "kaiserlich_solve_err_log"):
        sc.kaiserlich_solve_err_log = CollectionProperty(type=KaiserlichSolveErrItem)
    if not hasattr(sc, "kaiserlich_solve_err_idx"):
        sc.kaiserlich_solve_err_idx = IntProperty(name="Index", default=0, min=0)
    if not hasattr(sc, "kaiserlich_solve_attempts"):
        sc.kaiserlich_solve_attempts = IntProperty(name="Solve Attempts", default=0, min=0)
    if not hasattr(sc, "kaiserlich_solve_graph_enabled"):
        sc.kaiserlich_solve_graph_enabled = BoolProperty(
            name="Overlay Graph", default=True,
            description="Sparkline-Overlay des Avg-Errors im CLIP-Editor anzeigen"
        )
    if not hasattr(sc, "kaiserlich_debug_graph"):
        sc.kaiserlich_debug_graph = BoolProperty(
            name="Debug Graph", default=False,
            description="Konsolen-Logs für Solve-Overlay und Solve-Log aktivieren"
        )

def _unregister_scene_props() -> None:
    sc = bpy.types.Scene
    for name in (
        "repeat_frame", "marker_frame", "frames_track", "error_track",
        "kaiserlich_solve_err_log", "kaiserlich_solve_err_idx",
        "kaiserlich_solve_attempts", "kaiserlich_solve_graph_enabled",
        "kaiserlich_debug_graph",
    ):
        if hasattr(sc, name):
            try:
                delattr(sc, name)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Launcher-Operator: startet den modalen Coordinator
# ---------------------------------------------------------------------------
class CLIP_OT_kaiserlich_coordinator_launcher(BpyOperator):
    bl_idname = "clip.kaiserlich_coordinator_launcher"
    bl_label = "Kaiserlich Coordinator (Start)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.app.background:
            self.report({'ERROR'}, "Kein UI (Background). Blender normal starten.")
            return {'CANCELLED'}
        try:
            ret = bpy.ops.clip.tracking_coordinator('INVOKE_DEFAULT')
            if ret in ({'RUNNING_MODAL'}, {'FINISHED'}):
                self.report({'INFO'}, f"Coordinator gestartet: {ret}")
                return {'FINISHED'}
            self.report({'ERROR'}, f"Coordinator nicht gestartet: {ret}")
            return {'CANCELLED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Start fehlgeschlagen: {ex!r}")
            return {'CANCELLED'}

# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
class CLIP_PT_kaiserlich_panel(Panel):
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text="Tracking Einstellungen")
        if hasattr(scene, "marker_frame"):
            layout.prop(scene, "marker_frame")
        if hasattr(scene, "frames_track"):
            layout.prop(scene, "frames_track")
        if hasattr(scene, "error_track"):
            layout.prop(scene, "error_track")
        layout.separator()
        # Solve QA – Overlay + Tabelle
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Solve QA")
        row.prop(scene, "kaiserlich_solve_graph_enabled", text="Overlay")
        row.prop(scene, "kaiserlich_debug_graph", text="Debug")
        box.template_list(
            "KAISERLICH_UL_solve_err", "",  # UIList-ID
            scene, "kaiserlich_solve_err_log",
            scene, "kaiserlich_solve_err_idx",
            rows=5
        )
        layout.separator()
        layout.operator("clip.kaiserlich_coordinator_launcher", text="Coordinator starten")
# --- UIList für Solve-Log ---
class KAISERLICH_UL_solve_err(bpy.types.UIList):
    bl_idname = "KAISERLICH_UL_solve_err"
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.label(text=f"#{item.attempt:02d}")
        txt = "n/a" if item.value != item.value else f"{item.value:.3f}px"
        row.label(text=txt)
        row.label(text=item.stamp)

# ---------------------------------------------------------------------------
# Register/Unregister
# ---------------------------------------------------------------------------
_CLASSES = (
    RepeatEntry,
    KaiserlichSolveErrItem,
    KAISERLICH_UL_solve_err,
    CLIP_OT_tracking_coordinator,            # modal coordinator
    CLIP_OT_bidirectional_track,             # bidi helper
    CLIP_OT_kaiserlich_coordinator_launcher, # launcher
    CLIP_PT_kaiserlich_panel,                # ui
)

def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_scene_props()
    # Draw-Handler aktivieren
    global _solve_graph_handle
    if gpu is not None and _solve_graph_handle is None:
        _solve_graph_handle = bpy.types.SpaceClipEditor.draw_handler_add(
            _draw_solve_graph, (), 'WINDOW', 'POST_PIXEL'
        )

def unregister() -> None:
    # Draw-Handler entfernen
    global _solve_graph_handle
    if _solve_graph_handle is not None and gpu is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_solve_graph_handle, 'WINDOW')
        except Exception:
            pass
        _solve_graph_handle = None
    _unregister_scene_props()
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
