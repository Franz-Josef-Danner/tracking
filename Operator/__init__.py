import bpy

from .marker_helper_main import CLIP_OT_marker_helper_main

classes = (
    CLIP_OT_marker_helper_main,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
