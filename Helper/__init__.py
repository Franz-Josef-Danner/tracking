import bpy

from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .error_value import error_value
from .set_test_value import set_test_value
from .properties import RepeatEntry
from .log_helper import write_log_entry
from .find_max_marker_frame import get_active_marker_counts_sorted
from .clean_projection_error import clean_projection_error
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps, get_track_segments
from .naming import _safe_name
from .mute_ops import mute_marker_path, mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup
from .refine_high_error import run_refine_on_high_error
from .marker_adapt_helper import register as reg_adapt, unregister as unreg_adapt


__all__ = [
    # Solve-Exporte hier bewusst entfernt – lebt im Operator-Paket
    "run_refine_on_high_error",
]

classes = (
    RepeatEntry,
    CLIP_OT_enable_proxy,
    CLIP_OT_disable_proxy,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)
    reg_adapt()

def unregister():
    del bpy.types.Scene.repeat_frame
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unreg_adapt()


