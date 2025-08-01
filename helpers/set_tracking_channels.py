import bpy

class CLIP_OT_set_tracking_channels(bpy.types.Operator):
    """Setzt die aktivierten Tracking-Kanäle für RGB"""
    bl_idname = "clip.set_tracking_channels"
    bl_label = "Set RGB Tracking Channels"
    bl_options = {'REGISTER', 'UNDO'}

    use_red: bpy.props.BoolProperty(name="Red", default=True)
    use_green: bpy.props.BoolProperty(name="Green", default=True)
    use_blue: bpy.props.BoolProperty(name="Blue", default=True)

    def execute(self, context):
        # Clip holen – bevorzugt aus Clip Editor, sonst aus Scene
        clip = getattr(context.space_data, "clip", None) if context.space_data and context.space_data.type == 'CLIP_EDITOR' else None
        if clip is None:
            clip = context.scene.active_clip
        if clip is None:
            self.report({'ERROR'}, "Kein Movie Clip aktiv oder geladen")
            return {'CANCELLED'}

        tracking = clip.tracking.settings
        tracking.use_default_red_channel = self.use_red
        tracking.use_default_green_channel = self.use_green
        tracking.use_default_blue_channel = self.use_blue

        if context.area:
            context.area.tag_redraw()

        self.report({'INFO'}, f"Tracking-Kanäle gesetzt: R={self.use_red}, G={self.use_green}, B={self.use_blue}")
        return {'FINISHED'}
