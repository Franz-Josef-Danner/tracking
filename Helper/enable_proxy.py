import bpy

class CLIP_OT_enable_proxy(bpy.types.Operator):
    bl_idname = "clip.enable_proxy"
    bl_label = "Proxy aktivieren"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein gültiger Movie Clip gefunden.")
            return {'CANCELLED'}

        clip.use_proxy = True
        self.report({'INFO'}, "Proxy wurde aktiviert.")
        return {'FINISHED'}
