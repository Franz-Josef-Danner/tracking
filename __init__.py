# SPDX-License-Identifier: GPL-2.0-or-later
"""
Kaiserlich Tracker – Top-Level Add-on (__init__.py)
- Minimal: Scene-Properties + UI-Panel + schlanker Coordinator-Launcher
- Kein Auto-Bootstrap beim Enable
- Keine externen Registrare / Helper-Registrierung
"""
from __future__ import annotations

import bpy
from bpy.types import PropertyGroup, Panel, Operator
from bpy.props import IntProperty, FloatProperty, CollectionProperty

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Bootstrap-Launcher für Tracking-Workflow (UI-Knopf startet Coordinator)",
    "category": "Tracking",
}

# ---------------------------------------------------------------------------
# Datenmodelle (optional, belassen für spätere Nutzung)
# ---------------------------------------------------------------------------
class RepeatEntry(PropertyGroup):
    frame: IntProperty(
        name="Frame",
        description="Frame-Index, der mehrfach zu wenige Marker hatte",
        default=0,
        min=0,
    )
    count: IntProperty(
        name="Count",
        description="Anzahl Wiederholungen für diesen Frame",
        default=0,
        min=0,
    )

# ---------------------------------------------------------------------------
# Coordinator-Launcher (kein Modal): ruft ausschließlich bootstrap(context)
# ---------------------------------------------------------------------------
class CLIP_OT_tracking_coordinator(Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich Coordinator"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            # Import erst beim Aufruf: harte Kopplung vermeiden
            from .Operator.tracking_coordinator import bootstrap
            bootstrap(context)
            self.report({'INFO'}, "Bootstrap ausgeführt")
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Bootstrap fehlgeschlagen: {ex!r}")
            return {'CANCELLED'}

# ---------------------------------------------------------------------------
# UI-Panel (zeigt nur Properties + Start-Knopf)
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
        layout.operator("clip.tracking_coordinator", text="Start Coordinator", icon='PLAY')

# ---------------------------------------------------------------------------
# Scene-Properties
# ---------------------------------------------------------------------------
def _register_scene_props() -> None:
    sc = bpy.types.Scene
    if not hasattr(sc, "repeat_frame"):
        sc.repeat_frame = CollectionProperty(type=RepeatEntry)
    if not hasattr(sc, "marker_frame"):
        sc.marker_frame = IntProperty(
            name="Marker per Frame",
            default=25, min=10, max=50,
            description="Mindestanzahl Marker pro Frame",
        )
    if not hasattr(sc, "frames_track"):
        sc.frames_track = IntProperty(
            name="Frames per Track",
            default=25, min=5, max=100,
            description="Track-Länge in Frames",
        )
    if not hasattr(sc, "error_track"):
        sc.error_track = FloatProperty(
            name="Error-Limit (px)",
            description="Maximale tolerierte Reprojektion in Pixeln",
            default=2.0, min=0.1, max=10.0,
        )

def _unregister_scene_props() -> None:
    sc = bpy.types.Scene
    for name in ("repeat_frame", "marker_frame", "frames_track", "error_track"):
        if hasattr(sc, name):
            try:
                delattr(sc, name)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Register/Unregister
# ---------------------------------------------------------------------------
_CLASSES = (
    RepeatEntry,
    CLIP_OT_tracking_coordinator,
    CLIP_PT_kaiserlich_panel,
)

def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_scene_props()
    # Kein Auto-Bootstrap; Start ausschließlich via UI-Operator.

def unregister() -> None:
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _unregister_scene_props()

if __name__ == "__main__":
    register()
