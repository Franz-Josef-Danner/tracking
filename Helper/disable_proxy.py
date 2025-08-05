import bpy

class CLIP_OT_disable_proxy(bpy.types.Operator):
    bl_idname = "clip.disable_proxy"
    bl_label = "Proxy deaktivieren"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein gültiger Movie Clip gefunden.")
            return {'CANCELLED'}

        clip.use_proxy = False
        self.report({'INFO'}, "Proxy wurde deaktiviert.")
        return {'FINISHED'}
