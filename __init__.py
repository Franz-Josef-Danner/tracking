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

from .Operator.tracker_settings import CLIP_OT_tracker_settings
from .Operator.tracking_pipeline import CLIP_OT_tracking_pipeline
from .Helper.disable_proxy import CLIP_OT_disable_proxy
from .Helper.enable_proxy import CLIP_OT_enable_proxy
from .Operator.detect import CLIP_OT_detect_once
from .Operator.solve_camera import CLIP_OT_solve_watch_clean, run_solve_watch_clean
from .Operator.bidirectional_track import CLIP_OT_bidirectional_track
from .Operator.clean_short_tracks import CLIP_OT_clean_short_tracks
from .Operator.clean_error_tracks import CLIP_OT_clean_error_tracks
from .Operator.optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
from .Operator.main import CLIP_OT_main
from .Operator.main_to_adapt import CLIP_OT_main_to_adapt
from .Operator.marker_helper_main import CLIP_OT_marker_helper_main
from .Operator.find_low_marker_frame import CLIP_OT_find_low_marker_frame
from .Operator.jump_to_frame import CLIP_OT_jump_to_frame
from .Helper.properties import RepeatEntry

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
        layout.operator("clip.marker_helper_main", text="Track")

# Alle Klassen zur Registrierung
classes = (
    RepeatEntry,
    CLIP_OT_tracker_settings,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_disable_proxy,
    CLIP_OT_enable_proxy,
    CLIP_OT_detect_once,                           # ← WAR: CLIP_OT_detect
    CLIP_OT_solve_watch_clean,
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_clean_error_tracks,
    CLIP_OT_optimize_tracking_modal,
    CLIP_OT_find_low_marker_frame,
    CLIP_OT_main,
    CLIP_OT_main_to_adapt,
    CLIP_OT_jump_to_frame,
    CLIP_OT_marker_helper_main,
    CLIP_PT_kaiserlich_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


    # Custom Property für Frame-Tracking
    bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)

    # Eigenschaften für das UI
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker per Frame",
        default=25, min=10, max=50
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames per Track",
        default=25, min=5, max=100
    )
    bpy.types.Scene.error_track = FloatProperty(
        name="Error-Limit (px)",
        description="Maximale tolerierte Reprojektion in Pixeln",
        default=2.0, min=1.0, max=4.0,
    )

def unregister():
    # Properties entfernen
    del bpy.types.Scene.repeat_frame
    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
