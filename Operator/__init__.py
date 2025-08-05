import bpy

from .proxy_builder import CLIP_OT_proxy_builder
from .tracker_settings import CLIP_OT_tracker_settings
from .detect import CLIP_OT_detect
from .bidirectional_track import CLIP_OT_bidirectional_track

operator_classes = (
    CLIP_OT_proxy_builder,
    CLIP_OT_tracker_settings,
    CLIP_OT_detect,
    CLIP_OT_bidirectional_track,
)

def register():
    for cls in operator_classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(operator_classes):
        bpy.utils.unregister_class(cls)
if __name__ == "__main__":
    register()
