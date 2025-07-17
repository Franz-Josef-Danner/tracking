bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy

class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(OBJECT_OT_simple_operator)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_simple_operator)

if __name__ == "__main__":
    register()
