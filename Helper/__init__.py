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
