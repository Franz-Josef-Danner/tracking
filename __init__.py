# SPDX-License-Identifier: GPL-2.0-or-later
"""Kaiserlich Tracker – Top-Level Add-on (__init__.py), UI ausgelagert nach UI/."""
from __future__ import annotations
import bpy
from bpy.types import PropertyGroup, Operator as BpyOperator
from bpy.props import IntProperty, FloatProperty, CollectionProperty

from .Operator.camera_tracking_coordinator import CLIP_OT_camera_tracking_coordinator
from .Helper.bidirectional_track import CLIP_OT_bidirectional_track
from .Operator.bootstrap_O import CLIP_OT_bootstrap_cycle
from .Operator.find_frame_O import CLIP_OT_find_low_and_jump
from .Operator.detect_O import CLIP_OT_detect_cycle
from .Operator.clean_O import CLIP_OT_clean_cycle

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
# Scene-Properties (Workflow-Parameter)
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
    for name in ("repeat_frame", "marker_frame", "frames_track", "error_track"):
        if hasattr(sc, name):
            try:
                delattr(sc, name)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Launcher-Operator
# ---------------------------------------------------------------------------
class CLIP_OT_kaiserlich_coordinator_launcher(BpyOperator):
    bl_idname = "clip.kaiserlich_coordinator_launcher"
    bl_label = "Kaiserlich Coordinator (Start)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if bpy.app.background:
            self.report({'ERROR'}, "Kein UI (Background).")
            return {'CANCELLED'}
        return bpy.ops.clip.camera_tracking_coordinator('INVOKE_DEFAULT')


# ---------------------------------------------------------------------------
# Register/Unregister
# ---------------------------------------------------------------------------
_CLASSES = [
    RepeatEntry,
    # Helper/Support-Operatoren
    CLIP_OT_bootstrap_cycle,
    CLIP_OT_find_low_and_jump,
    CLIP_OT_detect_cycle,
    CLIP_OT_clean_cycle,
    # CLIP_OT_solve_test removed
    # Bidi + Coordinator + Launcher
    CLIP_OT_bidirectional_track,
    CLIP_OT_camera_tracking_coordinator,
    CLIP_OT_kaiserlich_coordinator_launcher,
]


def register() -> None:
    # UI-Paket registriert Panels & UI-Properties
    from .ui import register as _ui_register
    for c in _CLASSES:
        try:
            bpy.utils.register_class(c)
        except Exception:
            pass
    _register_scene_props()
    _ui_register()  # registriert UI-Panel und UI-Scene-Properties


def unregister() -> None:
    from .ui import unregister as _ui_unregister
    _ui_unregister()
    _unregister_scene_props()
    for c in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass


if __name__ == "__main__":
    register()
