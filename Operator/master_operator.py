import bpy


class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):


# Registration
classes = (
    KAISERLICHTRACKER_OT_master_operator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
