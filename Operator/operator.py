import bpy
from ..Helper.control import detect_cyclus

class CLIP_OT_kaiserlich_detect_cyclus(bpy.types.Operator):
    bl_idname = "clip.kaiserlich_detect_cyclus"
    bl_label = "Detect Cyclus"
    bl_description = "Starte einen adaptiven Feature-Detection-Zyklus"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            detect_cyclus(context)
        except Exception as e:
            self.report({'ERROR'}, f"Fehler: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

classes = (CLIP_OT_kaiserlich_detect_cyclus,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
