import bpy
import time

class ToggleProxyOperator(bpy.types.Operator):
    """Proxy/Timecode Umschalten"""
    bl_idname = "clip.toggle_proxy"
    bl_label = "Toggle Proxy/Timecode"

    def execute(self, context):
        clip = context.space_data.clip
        if clip:
            clip.use_proxy = not clip.use_proxy
            self.report({'INFO'}, f"Proxy/Timecode {'aktiviert' if clip.use_proxy else 'deaktiviert'}")
            time.sleep(2)
        else:
            self.report({'WARNING'}, "Kein Clip geladen")
        return {'FINISHED'}

def draw_proxy_button(self, context):
    layout = self.layout
    layout.operator(ToggleProxyOperator.bl_idname, text="Proxy/Timecode umschalten")

def register():
    bpy.utils.register_class(ToggleProxyOperator)
    bpy.types.CLIP_HT_header.append(draw_proxy_button)

def unregister():
    bpy.types.CLIP_HT_header.remove(draw_proxy_button)
    bpy.utils.unregister_class(ToggleProxyOperator)

if __name__ == "__main__":
    register()
