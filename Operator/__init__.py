import bpy

from .tracker_settings import CLIP_OT_tracker_settings
from .detect import CLIP_OT_detect_once            # <— war: CLIP_OT_detect
from .bidirectional_track import CLIP_OT_bidirectional_track
from .tracking_pipeline import CLIP_OT_tracking_pipeline
from .clean_error_tracks import CLIP_OT_clean_error_tracks
from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
from ..Helper.solve_camera_helper import CLIP_OT_solve_watch_clean
from .main_to_adapt import CLIP_OT_launch_main_with_adapt
from .main import CLIP_OT_main

try:
    from .clean_short_tracks import CLIP_OT_clean_short_tracks
except Exception as e:
    raise ImportError(f"CLIP_OT_clean_short_tracks Import fehlgeschlagen: {e}")

classes = (
    CLIP_OT_tracker_settings,
    CLIP_OT_detect_once,                         # <— war: CLIP_OT_detect
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_clean_error_tracks,
    CLIP_OT_optimize_tracking_modal,
    CLIP_OT_solve_watch_clean,
    CLIP_OT_launch_main_with_adapt,
    CLIP_OT_main,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
