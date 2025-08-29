import bpy

from .Operator.tracking_coordinator import register as _reg_coord, unregister as _unreg_coord

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
