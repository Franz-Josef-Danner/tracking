# SPDX-License-Identifier: GPL-2.0-or-later
"""
Kaiserlich Tracker – Top-Level Add-on (__init__.py)
- UI-Panel im CLIP_EDITOR
- Scene-Properties
- Delegiert Registrierung an Helper + Coordinator
- Robuste optionale Importe, keine _classes-NameError mehr
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

# --- Registrare (robust) -----------------------------------------------------
try:
    from .Operator.tracking_coordinator import register as _reg_coord, unregister as _unreg_coord
except Exception:
    _reg_coord = _unreg_coord = None  # type: ignore

try:
    from .Helper import register as _reg_helper, unregister as _unreg_helper
except Exception:
    _reg_helper = _unreg_helper = None  # type: ignore

# Optional: symbolischer Import – darf fehlen
try:  # noqa: SIM105
    from .Helper import bidirectional_track  # type: ignore  # pylint: disable=unused-import
except Exception:  # pragma: no cover
    bidirectional_track = None  # type: ignore

# Optional: nur für Typ-/ID-Existenz; kein Muss
try:
    from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator  # noqa: F401
except Exception:
    CLIP_OT_tracking_coordinator = None  # type: ignore


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
        # Properties können bei fehlerhafter Registrierung fehlen → defensiv zeichnen
        if hasattr(scene, "marker_frame"):
            layout.prop(scene, "marker_frame")
        if hasattr(scene, "frames_track"):
            layout.prop(scene, "frames_track")
        if hasattr(scene, "error_track"):
            layout.prop(scene, "error_track")

        layout.separator()
        # Button existiert nur, wenn Operator registriert ist
        ops = getattr(bpy.ops, "clip", None)
        if ops and hasattr(ops, "tracking_coordinator"):
            layout.operator("clip.tracking_coordinator", text="Track")
        else:
            col = layout.column()
            col.enabled = False
            col.operator("wm.call_menu", text="Track (Operator fehlt)")


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

    # 3) Externe Registrare (nur wenn vorhanden)
    if _reg_helper:
        _reg_helper()
    if _reg_coord:
        _reg_coord()

    print("[Kaiserlich] register OK")


def unregister() -> None:
    # 1) Externe Deregistrare zuerst (Operator clean entfernen)
    if _unreg_coord:
        _unreg_coord()
    if _unreg_helper:
        _unreg_helper()

    # 2) Scene-Properties
    _unregister_scene_props()

    # 3) Lokale Klassen
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    print("[Kaiserlich] unregister OK")


if __name__ == "__main__":
    register()
