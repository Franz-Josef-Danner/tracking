# SPDX-License-Identifier: GPL-2.0-or-later
"""Kaiserlich Tracker – Reduzierter Start/Panel für Detect-only."""
from __future__ import annotations
import bpy
from bpy.types import Panel, Operator as BpyOperator
from bpy.props import IntProperty
from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Launcher für den reduzierten Detect-only Workflow",
    "category": "Tracking",
}

def _register_scene_props() -> None:
    sc = bpy.types.Scene
    if not hasattr(sc, "marker_frame"):
        sc.marker_frame = IntProperty(
            name="Marker per Frame", default=25, min=10, max=100,
            description="Zielgröße für Detect-only",
        )

class CLIP_OT_kaiserlich_coordinator_launcher(BpyOperator):
    bl_idname = "clip.kaiserlich_coordinator_launcher"
    bl_label = "Kaiserlich Coordinator (Start)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        if bpy.app.background:
            self.report({'ERROR'}, "Kein UI (Background).")
            return {'CANCELLED'}
        return bpy.ops.clip.tracking_coordinator('INVOKE_DEFAULT')

class CLIP_PT_kaiserlich_panel(Panel):
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text="Detect-only Einstellungen")
        if hasattr(scene, "marker_frame"):
            layout.prop(scene, "marker_frame")
        layout.operator("clip.kaiserlich_coordinator_launcher", text="Coordinator starten")

_CLASSES = (
    CLIP_OT_tracking_coordinator,
    CLIP_OT_kaiserlich_coordinator_launcher,
    CLIP_PT_kaiserlich_panel,
)

def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_scene_props()

def unregister() -> None:
    # Scene-Props entfernen
    sc = bpy.types.Scene
    for name in ("marker_frame",):
        if hasattr(sc, name):
            try:
                delattr(sc, name)
            except Exception:
                pass
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
