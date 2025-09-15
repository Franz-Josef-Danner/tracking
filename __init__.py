# SPDX-License-Identifier: GPL-2.0-or-later
"""Kaiserlich Tracker – Top-Level Add-on (__init__.py) ohne Grafik-Overlay."""
from __future__ import annotations
import bpy
from bpy.types import PropertyGroup, Panel, Operator as BpyOperator
from bpy.props import IntProperty, FloatProperty, CollectionProperty, BoolProperty, StringProperty

# WICHTIG: nur Klassen importieren, kein register() von Submodulen aufrufen
from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator
from .Helper.bidirectional_track import CLIP_OT_bidirectional_track

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Launcher + UI für den Kaiserlich Tracking-Workflow (ohne Overlay)",
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
# Öffentliche Helper-Funktion (vom Coordinator aufrufbar) – Wrapper in ui.solve_log
def kaiserlich_solve_log_add(context: bpy.types.Context, value: float | None) -> None:
    from .ui.solve_log import kaiserlich_solve_log_add as _impl
    _impl(context, value)
    
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
    if not hasattr(sc, "kaiserlich_debug_graph"):
        sc.kaiserlich_debug_graph = BoolProperty(
            name="Debug Graph", default=False,
            description="Konsolen-Logs für Solve-Log aktivieren"
        )
    if not hasattr(sc, "kaiserlich_solve_log_max_rows"):
        sc.kaiserlich_solve_log_max_rows = IntProperty(
            name="Max Rows",
            default=30,
            min=1,
            max=200,
            description="Maximalzeilen für die Solve-Log-Liste (Panel-Höhenlimit)",
        )

def _unregister_scene_props() -> None:
    sc = bpy.types.Scene
    for name in (
        "repeat_frame", "marker_frame", "frames_track", "error_track",
        "kaiserlich_solve_err_log", "kaiserlich_solve_err_idx",
        "kaiserlich_solve_attempts",
        "kaiserlich_debug_graph", "kaiserlich_solve_log_max_rows",
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
            self.report({'ERROR'}, "Kein UI (Background).")
            return {'CANCELLED'}
        return bpy.ops.clip.tracking_coordinator('INVOKE_DEFAULT')

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
        # Solve QA – Log
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Solve QA")
        row.prop(scene, "kaiserlich_debug_graph", text="Debug")
        coll = getattr(scene, "kaiserlich_solve_err_log", None)
        max_rows = int(getattr(scene, "kaiserlich_solve_log_max_rows", 30))
        rows = 1
        if coll is not None:
            rows = max(1, min(len(coll), max_rows))
        box.template_list(
            "KAISERLICH_UL_solve_err", "",  # UIList-ID
            scene, "kaiserlich_solve_err_log",
            scene, "kaiserlich_solve_err_idx",
            rows=rows
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
    CLIP_OT_tracking_coordinator,   # modal coordinator
    CLIP_OT_bidirectional_track,    # bidi helper
    CLIP_OT_kaiserlich_coordinator_launcher,  # launcher
    CLIP_PT_kaiserlich_panel,       # ui
)

def register() -> None:
    from .ui import register as _ui_register  # Stub
    # 1) Klassen zuerst registrieren (damit bl_rna existiert)
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    # 2) Dann Scene-Properties anlegen (nutzt registrierte PropertyGroups)
    _register_scene_props()
    _ui_register()  # Stub (keine Panels/Handler)

def unregister() -> None:
    from .ui import unregister as _ui_unregister  # Stub
    _ui_unregister()
    # 1) Scene-Properties zuerst sauber entfernen (lösen Referenzen)
    _unregister_scene_props()
    # 2) Dann Klassen deregistrieren
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
