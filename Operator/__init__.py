import bpy

from .tracker_settings import CLIP_OT_tracker_settings
from .detect import CLIP_OT_detect_once
from .bidirectional_track import CLIP_OT_bidirectional_track
from .tracking_pipeline import CLIP_OT_tracking_pipeline
from .clean_error_tracks import CLIP_OT_clean_error_tracks
from .marker_helper_main import CLIP_OT_marker_helper_main
from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
from .solve_camera import CLIP_OT_solve_watch_clean, run_solve_watch_clean  # ✅ KORREKT
from .main_to_adapt_helper import main_to_adapt_helper
from .main import CLIP_OT_main
from .jump_to_frame import CLIP_OT_jump_to_frame
from .find_low_marker_frame import CLIP_OT_find_low_marker_frame

try:
    from .clean_short_tracks import CLIP_OT_clean_short_tracks
    _HAS_CLEAN_SHORT = True
except Exception as e:
    print(f"[WARN] clean_short_tracks nicht geladen: {e}")
    _HAS_CLEAN_SHORT = False


classes = (
    CLIP_OT_tracker_settings,
    CLIP_OT_detect_once,
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_clean_error_tracks,
    CLIP_OT_marker_helper_main,
    CLIP_OT_optimize_tracking_modal,
    CLIP_OT_solve_watch_clean,          # ✅ genau einmal
    CLIP_OT_main_to_adapt,
    CLIP_OT_main,
    CLIP_OT_jump_to_frame,
    CLIP_OT_find_low_marker_frame,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
