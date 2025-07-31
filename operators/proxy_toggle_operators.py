import bpy

from ..helpers import enable_proxy, disable_proxy


class CLIP_OT_proxy_enable(bpy.types.Operator):
    bl_idname = "clip.proxy_enable"
    bl_label = "Proxy on"
    bl_description = "Aktiviert Proxy f\u00fcr den aktuellen Clip"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        enable_proxy(clip)
        self.report({'INFO'}, "Proxy aktiviert")
        return {'FINISHED'}


class CLIP_OT_proxy_disable(bpy.types.Operator):
    bl_idname = "clip.proxy_disable"
    bl_label = "Proxy off"
    bl_description = "Deaktiviert Proxy f\u00fcr den aktuellen Clip"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        disable_proxy(clip)
        self.report({'INFO'}, "Proxy deaktiviert")
        return {'FINISHED'}

