import bpy

class CLIP_OT_clear_custom_cache(bpy.types.Operator):
    bl_idname = "clip.clear_custom_cache"
    bl_label = "Clear RAM Cache"
    bl_description = "Reloads the clip to clear its RAM cache"

    def execute(self, context):
        sc = context.space_data
        if sc and sc.clip:
            bpy.ops.clip.reload()
            self.report({'INFO'}, f"RAM‑Cache für Clip '{sc.clip.name}' wurde geleert")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Kein Clip aktiv im Editor")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(CLIP_OT_clear_custom_cache)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_clear_custom_cache)

if __name__ == "__main__":
    register()