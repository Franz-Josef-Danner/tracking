import bpy

class CLIP_PT_clear_cache_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Cache Tools'
    bl_label = 'Clear Cache'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.clear_custom_cache", text="Clear RAM Cache", icon='TRASH')


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
    bpy.utils.register_class(CLIP_PT_clear_cache_panel)
    bpy.utils.register_class(CLIP_OT_clear_custom_cache)

def unregister():
    bpy.utils.unregister_class(CLIP_PT_clear_cache_panel)
    bpy.utils.unregister_class(CLIP_OT_clear_custom_cache)

if __name__ == "__main__":
    register()