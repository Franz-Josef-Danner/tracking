import bpy

def set_tracking_channels(red=True, green=True, blue=True):
    """Hilfsfunktion zum direkten Setzen der RGB-Kanäle (ohne UI)."""
    clip = bpy.context.edit_movieclip or bpy.context.scene.active_clip
    if not clip:
        print("❌ Kein Movie Clip aktiv oder geladen")
        return {'CANCELLED'}

    tracking = clip.tracking.settings
    tracking.use_default_red_channel = red
    tracking.use_default_green_channel = green
    tracking.use_default_blue_channel = blue

    print(f"✅ Tracking-Kanäle gesetzt: R={red}, G={green}, B={blue}")
    return {'FINISHED'}

class CLIP_OT_set_tracking_channels(bpy.types.Operator):
    """Setzt die aktivierten Tracking-Kanäle für RGB"""
    bl_idname = "clip.set_tracking_channels"
    bl_label = "Set RGB Tracking Channels"
    bl_options = {'REGISTER', 'UNDO'}

    use_red: bpy.props.BoolProperty(name="Red", default=True)
    use_green: bpy.props.BoolProperty(name="Green", default=True)
    use_blue: bpy.props.BoolProperty(name="Blue", default=True)

    def execute(self, context):
        result = set_tracking_channels(
            red=self.use_red,
            green=self.use_green,
            blue=self.use_blue
        )

        if context.area:
            context.area.tag_redraw()

        return result
