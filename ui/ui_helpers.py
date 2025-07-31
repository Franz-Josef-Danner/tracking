import bpy


class CLIP_OT_marker_status_popup(bpy.types.Operator):
    """Zeigt Statusmeldungen zum Tracking als Popup"""

    bl_idname = "clip.marker_status_popup"
    bl_label = "Tracking Feedback"

    message: bpy.props.StringProperty()

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_popup(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.label(text="🔍 Tracking Feedback:")
        for line in self.message.split("\n"):
            layout.label(text=line)

