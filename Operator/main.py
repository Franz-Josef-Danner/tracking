import bpy

class CLIP_OT_proxy_builder(bpy.types.Operator):
    """Proxy Builder für Clip Tracking Setup"""
    bl_idname = "clip.proxy_builder"
    bl_label = "Build Proxy Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. Proxy deaktivieren
        bpy.ops.clip.disable_proxy()

        # 2. Tracker Settings setzen
        bpy.ops.clip.tracker_settings()

        # 3. Marker Setup ausführen
        bpy.ops.clip.marker_helper_main()

        self.report({'INFO'}, "Proxy Setup erfolgreich ausgeführt")
        return {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(CLIP_OT_proxy_builder)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_proxy_builder)

if __name__ == "__main__":
    register()
