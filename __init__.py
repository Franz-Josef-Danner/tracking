bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor mit Eingaben für Tracking",
    "category": "Tracking",
}

import bpy
from bpy.props import IntProperty, FloatProperty

# Operator-Importe
from .Operator.proxy_builder import CLIP_OT_proxy_builder
from .Operator.tracker_settings import CLIP_OT_tracker_settings
from .Helper.marker_helper_main import CLIP_OT_marker_helper_main
from .Operator.detect import CLIP_OT_detect
from .Helper.disable_proxy import CLIP_OT_disable_proxy
from .Helper.enable_proxy import CLIP_OT_enable_proxy
from .Operator.bidirectional_track import CLIP_OT_bidirectional_track
# -------------------------------------
# Panel für das UI im Clip Editor
# -------------------------------------

class CLIP_PT_kaiserlich_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
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
        layout.operator("n", text="Track")

# -------------------------------------
# Registrierung der Klassen
# -------------------------------------

classes = (
    CLIP_PT_kaiserlich_panel,
    CLIP_OT_proxy_builder,
    CLIP_OT_tracker_settings,
    CLIP_OT_marker_helper_main,
    CLIP_OT_detect,
    CLIP_OT_disable_proxy,
    CLIP_OT_enable_proxy,
    CLIP_OT_bidirectional_track,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Eigenschaften für das Panel
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker per Frame",
        default=20,
        min=10,
        max=50
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames per Track",
        default=20,
        min=5,
        max=100
    )
    bpy.types.Scene.error_track = FloatProperty(
        name="Tracking Error",
        default=0.50,
        min=0.01,
        max=1.00,
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Eigenschaften entfernen
    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track

# Nur für Direktstart
if __name__ == "__main__":
    register()
