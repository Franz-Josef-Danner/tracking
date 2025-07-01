import bpy

class TRACK_OT_auto_track_forward(bpy.types.Operator):
    """Track all currently selected markers forward."""

    bl_idname = "clip.auto_track_forward"
    bl_label = "Auto Track Selected"
    bl_description = "Trackt alle ausgewählten Marker automatisch vorwärts"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Marker vorhanden")
            return {'CANCELLED'}

        bpy.ops.clip.track_markers(sequence=True)
        return {'FINISHED'}

class TRACK_PT_auto_track_panel(bpy.types.Panel):
    """UI panel for the auto-track operator."""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = "Auto Track"

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.auto_track_forward", icon='TRACKING_FORWARDS')

classes = [
    TRACK_OT_auto_track_forward,
    TRACK_PT_auto_track_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
