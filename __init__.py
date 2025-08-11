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

# Importiere Operatoren
from .Operator.tracker_settings import CLIP_OT_tracker_settings
from .Operator.tracking_pipeline import CLIP_OT_tracking_pipeline
from .Helper.marker_helper_main import CLIP_OT_marker_helper_main
from .Helper.disable_proxy import CLIP_OT_disable_proxy
from .Helper.enable_proxy import CLIP_OT_enable_proxy
from .Operator.detect import CLIP_OT_detect
from .Operator.bidirectional_track import CLIP_OT_bidirectional_track
from .Operator.clean_short_tracks import CLIP_OT_clean_short_tracks
from .Operator.clean_error_tracks import CLIP_OT_clean_error_tracks
from .Operator.optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
from .Operator.main import CLIP_OT_main
from .Helper.solve_camera_helper import CLIP_OT_solve_camera_helper

# Importiere PropertyGroup
from .Helper.properties import RepeatEntry  # ✅ NEU

# Panel
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
        layout.operator("CLIP.main", text="Track")

# Alle Klassen zur Registrierung
classes = (
    RepeatEntry,  # ✅ zuerst registrieren
    CLIP_PT_kaiserlich_panel,
    CLIP_OT_tracker_settings,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_marker_helper_main,
    CLIP_OT_disable_proxy,
    CLIP_OT_enable_proxy,
    CLIP_OT_detect,
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_clean_error_tracks,
    CLIP_OT_optimize_tracking_modal,
    CLIP_OT_main,
    CLIP_OT_solve_camera_helper,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Custom Property für Frame-Tracking
    bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)  # ✅ NEU

    # Eigenschaften für das UI
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
        default=0.500,
        min=0.001,
        max=1.000,
    )

def unregister():
    # Properties entfernen
    del bpy.types.Scene.repeat_frame  # ✅ NEU
    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
