from __future__ import annotations
import bpy

from .error_value import error_value
from .set_test_value import set_test_value
from .properties import RepeatEntry
from .find_low_marker_frame import run_find_low_marker_frame
from .jump_to_frame import run_jump_to_frame
from .detect import perform_marker_detection, run_detect_adaptive, run_detect_once
from .bidirectional_track import run_bidirectional_track, CLIP_OT_bidirectional_track
from .clean_short_tracks import clean_short_tracks
from .clean_error_tracks import run_clean_error_tracks
from .solve_camera import solve_watch_clean, run_solve_watch_clean
from .find_max_marker_frame import get_active_marker_counts_sorted
from .projection_cleanup_builtin import builtin_projection_cleanup, find_clip_window
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps, get_track_segments
from .naming import _safe_name
from .tracker_settings import apply_tracker_settings
from .mute_ops import mute_marker_path, mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup
from .refine_high_error import run_refine_on_high_error
from .marker_adapt_helper import run_marker_adapt_boost
from .marker_helper_main import marker_helper_main
# Nur was für die Registrierung wirklich nötig ist:
try:
    from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
except Exception:
    CLIP_OT_optimize_tracking_modal = None

# Optional: Scene-Collection für Repeat-Tracking (falls ihr sie nutzt)
try:
    from .properties import RepeatEntry
except Exception:
    RepeatEntry = None

__all__ = (
    "register",
    "unregister",
    "CLIP_OT_optimize_tracking_modal",
)

_classes = []
if CLIP_OT_optimize_tracking_modal is not None:
    _classes.append(CLIP_OT_optimize_tracking_modal)

def _register_scene_props():
    if RepeatEntry is not None and not hasattr(bpy.types.Scene, "repeat_frame"):
        bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)

def _unregister_scene_props():
    if hasattr(bpy.types.Scene, "repeat_frame"):
        del bpy.types.Scene.repeat_frame

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    _register_scene_props()
    print("[Helper] register() OK")

def unregister():
    _unregister_scene_props()
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    print("[Helper] unregister() OK")
