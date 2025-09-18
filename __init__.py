# SPDX-License-Identifier: GPL-2.0-or-later
"""Kaiserlich Tracker – Top-Level Add-on (__init__.py), Solve-QA-UI entfernt."""
from __future__ import annotations
import bpy
from bpy.types import PropertyGroup, Panel, Operator as BpyOperator
from bpy.props import IntProperty, FloatProperty, CollectionProperty

# Nur Klassen importieren – kein register() aus Submodulen aufrufen
from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator
from .Helper.bidirectional_track import CLIP_OT_bidirectional_track
# Neue delegierte Operatoren explizit importieren, damit sie in Blender registriert werden
from .Operator.bootstrap_O import CLIP_OT_bootstrap_cycle
from .Operator.find_frame_O import CLIP_OT_find_low_and_jump
from .Operator.detect_O import CLIP_OT_detect_cycle
from .Operator.clean_O import CLIP_OT_clean_cycle
from .Operator.solve_O import CLIP_OT_solve_cycle

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 1),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Launcher + UI für den Kaiserlich Tracking-Workflow",
    "category": "Tracking",
}

# ---------------------------------------------------------------------------
# Scene-Properties (bereinigt: keine Solve-QA-/Debug-/Log-Props mehr)
# ---------------------------------------------------------------------------
class RepeatEntry(PropertyGroup):
    frame: IntProperty(name="Frame", default=0, min=0)
    count: IntProperty(name="Count", default=0, min=0)


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


def _unregister_scene_props() -> None:
    sc = bpy.types.Scene
    for name in (
        "repeat_frame",
        "marker_frame",
        "frames_track",
        "error_track",
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
# Panel (bereinigt: nur Eingabefelder + Start-Button)
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
        layout.operator("clip.kaiserlich_coordinator_launcher", text="Coordinator starten")


# ---------------------------------------------------------------------------
# Register/Unregister
# ---------------------------------------------------------------------------
_CLASSES = (
    RepeatEntry,
    # Helper/Support-Operatoren zuerst registrieren
    CLIP_OT_bootstrap_cycle,
    CLIP_OT_find_low_and_jump,
    CLIP_OT_detect_cycle,
    CLIP_OT_clean_cycle,
    CLIP_OT_solve_cycle,
    # Bidi + Coordinator + UI
    CLIP_OT_bidirectional_track,
    CLIP_OT_tracking_coordinator,            # modal coordinator
    CLIP_OT_kaiserlich_coordinator_launcher, # launcher
    CLIP_PT_kaiserlich_panel,                # ui
)


def register() -> None:
    from .ui import register as _ui_register  # weiter im separaten ui/ Ordner
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_scene_props()
    _ui_register()                           # Stub ok


def unregister() -> None:
    from .ui import unregister as _ui_unregister
    _ui_unregister()
    _unregister_scene_props()
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
