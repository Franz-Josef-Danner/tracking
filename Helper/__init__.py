import bpy

from .marker_helper_main import CLIP_OT_marker_helper_main
from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .error_value import error_value
from .set_test_value import set_test_value
from .find_low_marker_frame import find_low_marker_frame
from .jump_to_frame import jump_to_frame
from .properties import RepeatEntry
from .log_helper import write_log_entry
from .solve_kamera_helper import CLIP_OT_solve_watch_clean

from .find_max_marker_frame import get_active_marker_counts_sorted
from .prune_tracks_density import prune_tracks_density
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .prune_tracks_density import prune_tracks_density
from .segments import track_has_internal_gaps, get_track_segments
from .naming import _safe_name
from .mute_ops import mute_marker_path, mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

# Alle Klassen in eine Liste
classes = (
    RepeatEntry,
    CLIP_OT_marker_helper_main,
    CLIP_OT_enable_proxy,
    CLIP_OT_disable_proxy,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)

def unregister():
    del bpy.types.Scene.repeat_frame
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
