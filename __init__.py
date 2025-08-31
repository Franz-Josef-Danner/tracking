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
    # Nur numerische Endwerte zulassen
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
    # Neuester Eintrag ganz nach oben (Index 0)
    try:
        coll = scn.kaiserlich_solve_err_log
        coll.move(len(coll) - 1, 0)
        scn.kaiserlich_solve_err_idx = 0
    except Exception:
        pass
    # UI-Refresh (CLIP-Editor + Sidebar)
    _tag_clip_redraw()
# GPU-Overlay (Sparkline) – Draw Handler
_solve_graph_handle = None
def _draw_solve_graph():
    if gpu is None:
        return
    scn = getattr(bpy.context, "scene", None)
    if not scn or not getattr(scn, "kaiserlich_solve_graph_enabled", False):
        return
    coll = getattr(scn, "kaiserlich_solve_err_log", [])
    # Chronologische Reihenfolge erzwingen (ältester→neuester), NaN ignorieren
    seq = sorted((it.attempt, it.value) for it in coll if it.value == it.value)
    if not seq:
        return
    vals = [v for _, v in seq]
    vmin, vmax = min(vals), max(vals)
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-12
    # Viewport-Maße robust beschaffen (Region ist nicht garantiert gesetzt)
    try:
        _vx, _vy, W, H = gpu.state.viewport_get()
    except Exception:
        region = getattr(bpy.context, "region", None)
        if not region:
            return
        W, H = region.width, region.height
    pad = 16
    gw, gh = min(320, W - 2*pad), 80
    ox, oy = W - gw - pad, pad
    # Letzte 200 Punkte (chronologisch)
    take = seq[-200:]
    n = len(take)
    ln = max(1, n - 1)  # vermeidet Div/0, erlaubt 1-Punkt-Stub
    coords = []
    for i, (_att, val) in enumerate(take):
        x = ox + (i / ln) * gw
        y = oy + ((val - vmin) / (vmax - vmin)) * gh
        coords.append((x, y))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    # Rahmen
    box = [(ox, oy), (ox+gw, oy), (ox+gw, oy+gh), (ox, oy+gh)]
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.35)); batch.draw(shader)
    # Kurve
    # Bei nur einem Punkt einen 1px-Stub zeichnen, damit sichtbar
    if len(coords) == 1:
        coords.append((coords[0][0] + 1, coords[0][1]))
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.9)); batch.draw(shader)

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

def _unregister_scene_props() -> None:
    sc = bpy.types.Scene
    for name in (
        "repeat_frame", "marker_frame", "frames_track", "error_track",
        "kaiserlich_solve_err_log", "kaiserlich_solve_err_idx",
        "kaiserlich_solve_attempts", "kaiserlich_solve_graph_enabled",
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
        box.template_list(
            "KAISERLICH_UL_solve_err", "",  # UIList-ID
            scene, "kaiserlich_solve_err_log",
            scene, "kaiserlich_solve_err_idx",
            rows=5
        )
        box.operator("kaiserlich.clear_solve_err", icon="TRASH", text="Clear Solve Log")
        layout.separator()
        layout.operator("clip.kaiserlich_coordinator_launcher", text="Coordinator starten")
# --- UIList & Operator für Solve-Log ---
class KAISERLICH_UL_solve_err(bpy.types.UIList):
    bl_idname = "KAISERLICH_UL_solve_err"
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.label(text=f"#{item.attempt:02d}")
        txt = "n/a" if item.value != item.value else f"{item.value:.3f}px"
        row.label(text=txt)
        row.label(text=item.stamp)

class KAISERLICH_OT_ClearSolveErr(BpyOperator):
    bl_idname = "kaiserlich.clear_solve_err"
    bl_label = "Clear Solve Log"
    bl_options = {"INTERNAL"}
    # optional: State für Dialoganzeige (keine Property nötig)
    _count: int = 0

    def invoke(self, context, event):
        scn = context.scene
        self._count = len(getattr(scn, "kaiserlich_solve_err_log", []))
        # Fast-Path: mit Ctrl oder Shift sofort löschen, ohne Dialog
        if event and (getattr(event, "ctrl", False) or getattr(event, "shift", False)):
            return self.execute(context)
        # Bestätigungsdialog anzeigen
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, _context):
        col = self.layout.column(align=True)
        col.label(text=f"{self._count} Einträge löschen?")
        col.label(text="Dies setzt auch den Solve-Zähler zurück.", icon="INFO")

    def execute(self, context):
        scn = context.scene
        try:
            scn.kaiserlich_solve_err_log.clear()
            scn.kaiserlich_solve_attempts = 0
        finally:
            _tag_clip_redraw()
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# Register/Unregister
# ---------------------------------------------------------------------------
_CLASSES = (
    RepeatEntry,
    KaiserlichSolveErrItem,
    KAISERLICH_UL_solve_err,
    KAISERLICH_OT_ClearSolveErr,
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
