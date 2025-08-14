import bpy

from .marker_helper_main import CLIP_OT_marker_helper_main
from .tracking_coordinator import CLIP_OT_tracking_coordinator

classes = (
    CLIP_OT_marker_helper_main,
    CLIP_OT_tracking_coordinator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
