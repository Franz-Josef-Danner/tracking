bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 5),
    "blender": (3, 6, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy
import os
import shutil

class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}


class CLIP_OT_panel_button(bpy.types.Operator):
    bl_idname = "clip.panel_button"
    bl_label = "Panel Button"
    bl_description = "Erstellt Proxy-Dateien mit 50% Gr\u00f6\u00dfe"

    def execute(self, context):
        clip = context.space_data.clip

        clip.use_proxy = True

        clip.proxy.build_25 = False
        clip.proxy.build_50 = True
        clip.proxy.build_75 = False
        clip.proxy.build_100 = False

        # Proxy mit Qualität 50 erzeugen
        clip.proxy.quality = 50

        if hasattr(clip.proxy, "use_proxy_custom_directory"):
            clip.proxy.use_proxy_custom_directory = True
        else:
            clip.proxy.use_custom_directory = True
        clip.proxy.directory = "//proxies"

        # absoluten Pfad zum Proxy-Verzeichnis auflösen
        proxy_dir = bpy.path.abspath(clip.proxy.directory)
        project_dir = bpy.path.abspath("//")

        # nur löschen, wenn das Verzeichnis innerhalb des Projektes liegt
        if os.path.abspath(proxy_dir).startswith(os.path.abspath(project_dir)):
            if os.path.exists(proxy_dir):
                try:
                    shutil.rmtree(proxy_dir)
                except Exception as e:
                    self.report({'WARNING'}, f"Fehler beim L\u00f6schen des Proxy-Verzeichnisses: {e}")

        # Blender-Operator zum Erzeugen der Proxys aufrufen
        bpy.ops.clip.rebuild_proxy()

        self.report({'INFO'}, "Proxy auf 50% erstellt")
        return {'FINISHED'}


class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon Informationen")


class CLIP_PT_button_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Button Panel'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.panel_button')

classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_PT_tracking_panel,
    CLIP_PT_button_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
