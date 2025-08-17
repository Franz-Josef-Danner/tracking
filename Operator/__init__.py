import bpy

from .tracking_coordinator import CLIP_OT_tracking_coordinator
from .clip_clean_error_tracks_modular import CLIP_OT_clean_error_tracks_modular

classes = (
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
