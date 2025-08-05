import bpy

class CLIP_OT_proxy_disable(bpy.types.Operator):
    bl_idname = "clip.proxy_disable"
    bl_label = "Proxy deaktivieren"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein gültiger Movie Clip gefunden.")
            return {'CANCELLED'}

        clip.use_proxy = False
        self.report({'INFO'}, "Proxy wurde deaktiviert.")
        return {'FINISHED'}
