bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich",
    "description": "Adaptive automatische Feature- / Marker-Detection mit Zyklensteuerung",
    "category": "Tracking"
}

import importlib
import bpy

from . import ui, operator as op_module, helpers

# Hot-reload Untermodule bei Skript-Neuladen in Blender
if "_KAISERLICH_RELOADED" in locals():  # type: ignore
    importlib.reload(ui)
    importlib.reload(op_module)
    importlib.reload(helpers)

_KAISERLICH_RELOADED = True  # Marker


classes = (
    ui.CLIP_PT_KaiserlichTracker,
    op_module.CLIP_OT_KaiserlichDetectCycle,
)


def register_properties():
    scene = bpy.types.Scene
    from bpy.props import IntProperty, BoolProperty

    if not hasattr(scene, "kaiserlich_marker_per_frame"):
        scene.kaiserlich_marker_per_frame = IntProperty(
            name="Marker / Frame",
            description="Angestrebte Anzahl neuer Marker pro Frame (Richtwert)",
            default=25,
            min=1,
            max=500
        )

    if not hasattr(scene, "kaiserlich_cycle_running"):
        scene.kaiserlich_cycle_running = BoolProperty(
            name="Cycle Running",
            description="Interner Status, um Mehrfachstarts zu verhindern",
            default=False
        )

    if not hasattr(scene, "kaiserlich_last_marker_count"):
        scene.kaiserlich_last_marker_count = IntProperty(
            name="Letzte Markeranzahl",
            description="Markeranzahl beim letzten erfolgreichen Zyklus",
            default=0,
            min=0
        )


def unregister_properties():
    scene = bpy.types.Scene
    for attr in [
        "kaiserlich_marker_per_frame",
        "kaiserlich_cycle_running",
        "kaiserlich_last_marker_count",
    ]:
        if hasattr(scene, attr):
            delattr(scene, attr)


def register():
    register_properties()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    unregister_properties()


if __name__ == "__main__":
    register()
