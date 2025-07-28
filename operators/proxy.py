import bpy
import os
import shutil


class CLIP_OT_proxy_on(bpy.types.Operator):
    bl_idname = "clip.proxy_on"
    bl_label = "Proxy on"
    bl_description = "Aktiviert das Proxy"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}
        clip.use_proxy = True
        self.report({'INFO'}, "Proxy aktiviert")
        return {'FINISHED'}


class CLIP_OT_proxy_off(bpy.types.Operator):
    bl_idname = "clip.proxy_off"
    bl_label = "Proxy off"
    bl_description = "Deaktiviert das Proxy"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}
        clip.use_proxy = False
        self.report({'INFO'}, "Proxy deaktiviert")
        return {'FINISHED'}


class CLIP_OT_panel_button(bpy.types.Operator):
    bl_idname = "clip.proxy_build"
    bl_label = "Proxy bauen"
    bl_description = "Erstellt Proxy-Dateien mit 50% Größe"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        clip.use_proxy = True
        clip.proxy.build_25 = False
        clip.proxy.build_50 = True
        clip.proxy.build_75 = False
        clip.proxy.build_100 = False
        clip.proxy.quality = 50
        clip.proxy.directory = "//proxies"

        proxy_dir = bpy.path.abspath(clip.proxy.directory)
        project_dir = bpy.path.abspath("//")
        if os.path.abspath(proxy_dir).startswith(os.path.abspath(project_dir)):
            if os.path.exists(proxy_dir):
                try:
                    shutil.rmtree(proxy_dir)
                except Exception as e:
                    self.report({'WARNING'}, f"Fehler beim Löschen des Proxy-Verzeichnisses: {e}")

        bpy.ops.clip.rebuild_proxy()
        self.report({'INFO'}, "Proxy auf 50% erstellt")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_proxy_on,
    CLIP_OT_proxy_off,
    CLIP_OT_panel_button,
)

