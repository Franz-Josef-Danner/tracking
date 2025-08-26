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

        # Defensiv: Operator nur anzeigen, wenn er registriert ist
        op_ok = hasattr(bpy.ops, "clip") and hasattr(bpy.ops.clip, "tracking_coordinator")
        if op_ok:
            layout.operator("clip.tracking_coordinator", text="Track")
        else:
            row = layout.row()
            row.enabled = False
            row.operator("wm.call_menu", text="Track (Operator fehlt)").name = ""
            # Optional: kleine Hilfe
            layout.label(text="Hinweis: Operator noch nicht registriert.", icon='INFO')


# --- Registrierung ------------------------------------------------------------

# Wichtig: Property-Klassen müssen VOR Scene-Properties registriert sein,
# Panels aber NACH allen Operatoren (Helper+Coordinator), damit deren draw()
# keinen 'unknown operator' verursacht.
_CLASSES_PROPS = (RepeatEntry,)
_CLASSES_UI = (CLIP_PT_kaiserlich_panel,)


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
    # 1) Property-Klassen
    for cls in _CLASSES_PROPS:
        bpy.utils.register_class(cls)

    # 2) Scene-Properties (benötigen RepeatEntry)
    _register_scene_props()

    # 3) Externe Registrare: zuerst Helper (diverse Operatoren), dann Coordinator
    _reg_helper()
    _reg_coord()

    # 4) UI-Panels GANZ ZUM SCHLUSS
    for cls in _CLASSES_UI:
        bpy.utils.register_class(cls)


def unregister() -> None:
    # 1) UI-Panels zuerst deregistrieren
    for cls in reversed(_CLASSES_UI):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    # 2) Externe Unregister
    _unreg_coord()
    _unreg_helper()

    # 3) Scene-Properties
    _unregister_scene_props()

    # 4) Property-Klassen zum Schluss deregistrieren
    for cls in reversed(_CLASSES_PROPS):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
