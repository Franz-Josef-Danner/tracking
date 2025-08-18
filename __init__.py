bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor mit Eingaben für Tracking",
    "category": "Tracking",
}

import bpy
from bpy.types import PropertyGroup, Panel
from bpy.props import IntProperty, FloatProperty, CollectionProperty

# Sub-Registrare (Aggregator-Import, keine Klassen direkt)
from .Operator import register as _reg_coord, unregister as _unreg_coord
from .Helper import register as _reg_helper, unregister as _unreg_helper

# --- Scene-PropertyGroup (Root verwaltet zentral die Scene-Props) ---
class RepeatEntry(PropertyGroup):
    frame: IntProperty(name="Frame", default=0, min=0)
    count: IntProperty(name="Count", default=0, min=0)

# --- UI-Panel ---
class CLIP_PT_kaiserlich_panel(Panel):
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text="Tracking Einstellungen")
        layout.prop(scene, "marker_frame")
        layout.prop(scene, "frames_track")
        layout.prop(scene, "error_track")
        layout.separator()
        layout.operator("clip.tracking_coordinator", text="Track")

# >>> einheitliche Variable VOR register()
_classes = (
    RepeatEntry,
    CLIP_PT_kaiserlich_panel,
)

def register():
    # 1) Lokale Klassen
    for cls in _classes:
        bpy.utils.register_class(cls)

    # 2) Scene-Properties
    if not hasattr(bpy.types.Scene, "repeat_frame"):
        bpy.types.Scene.repeat_frame = CollectionProperty(type=RepeatEntry)
    if not hasattr(bpy.types.Scene, "marker_frame"):
        bpy.types.Scene.marker_frame = IntProperty(
            name="Marker per Frame", default=25, min=10, max=50
        )
    if not hasattr(bpy.types.Scene, "frames_track"):
        bpy.types.Scene.frames_track = IntProperty(
            name="Frames per Track", default=25, min=5, max=100
        )
    if not hasattr(bpy.types.Scene, "error_track"):
        bpy.types.Scene.error_track = FloatProperty(
            name="Error-Limit (px)", default=2.0, min=0.1, max=10.0
        )

    # 3) Sub-Registrare
    _reg_helper()   # registriert u.a. clip.optimize_tracking_modal
    _reg_coord()    # registriert clip.tracking_coordinator

def unregister():
    # 1) Sub-Registrare zuerst
    _unreg_coord()
    _unreg_helper()

    # 2) Scene-Props sicher löschen
    if hasattr(bpy.types.Scene, "repeat_frame"):
        del bpy.types.Scene.repeat_frame
    if hasattr(bpy.types.Scene, "marker_frame"):
        del bpy.types.Scene.marker_frame
    if hasattr(bpy.types.Scene, "frames_track"):
        del bpy.types.Scene.frames_track
    if hasattr(bpy.types.Scene, "error_track"):
        del bpy.types.Scene.error_track

    # 3) Lokale Klassen deregistrieren
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
