import bpy

from . import proxy_helper, clip_helper, ram_helper

from .marker_helper_main import CLIP_OT_marker_helper_main
from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .error_value import error_value
from .set_test_value import set_test_value
from .find_low_marker_frame import find_low_marker_frame
from .jump_to_frame import jump_to_frame
from .properties import RepeatEntry
from .log_helper import write_log_entry
from ..Helper.process_marker_path import process_marker_path
from ..Helper.mute_invalid_segments import mute_invalid_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.ram_helper import RamGuard, register_bpy_timer


__all__ = [
    "RamGuard",
    "register_bpy_timer",
    "proxy_helper",
    "clip_helper",
    "ram_helper",
]
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
