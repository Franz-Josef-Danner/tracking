import bpy

class MyTrackingOperator(bpy.types.Operator):
    bl_idname = "wm.my_tracking_operator"
    bl_label = "Tracking Frame Finder"

    def execute(self, context):
        # Dein Skript-Logik hier einfügen
        self.report({'INFO'}, "Tracking-Skript ausgeführt")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(MyTrackingOperator)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Window", space_type='EMPTY')
        kmi = km.keymap_items.new(MyTrackingOperator.bl_idname, type='T', value='PRESS', ctrl=True, alt=True)

def unregister():
    bpy.utils.unregister_class(MyTrackingOperator)

if __name__ == "__main__":
    register()
