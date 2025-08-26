# SPDX-License-Identifier: GPL-2.0-or-later
"""
Kaiserlich Tracker – Top-Level Add-on (__init__.py)
- UI-Panel im CLIP_EDITOR
- Scene-Properties
- Delegiert Registrierung an Helper + Coordinator (ohne try/except)
- Keine optionalen/symbolischen Imports mehr
"""
from __future__ import annotations

import bpy
from bpy.types import PropertyGroup, Panel
from bpy.props import IntProperty, FloatProperty, CollectionProperty

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor mit Eingaben für Tracking",
    "category": "Tracking",
}

# --- Strikte, direkte Importe (fail-fast) -----------------------------------
from .Operator.tracking_coordinator import register as _reg_coord, unregister as _unreg_coord
from .Helper import register as _reg_helper, unregister as _unreg_helper


# --- Datenmodelle ------------------------------------------------------------
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


# --- UI-Panel ----------------------------------------------------------------
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

        layout.operator("clip.tracking_coordinator", text="Track")


# --- Registrierung ------------------------------------------------------------
_classes = (
    RepeatEntry,
    CLIP_PT_kaiserlich_panel,
)


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


def register() -> None:
    # 1) Lokale Klassen
    for cls in _classes:
        bpy.utils.register_class(cls)

    # 2) Scene-Properties
    _register_scene_props()

    # 3) Externe Registrare (direkt, ohne try/except)
    _reg_helper()
    _reg_coord()

def unregister() -> None:
    # 1) Externe Deregistrare zuerst
    _unreg_coord()
    _unreg_helper()

    # 2) Scene-Properties
    _unregister_scene_props()

    # 3) Lokale Klassen
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
