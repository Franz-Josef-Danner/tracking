import bpy

class TRACK_OT_auto_track_bidir(bpy.types.Operator):
    """Trackt ausgewählte Marker rückwärts und dann vorwärts vom aktuellen Frame aus"""

    bl_idname = "clip.auto_track_bidir"
    bl_label = "Auto Track Bidirektional"
    bl_description = "Trackt ausgewählte Marker zuerst rückwärts, dann vorwärts, und kehrt zum Startframe zurück"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip_editor = context.space_data
        clip = clip_editor.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Marker vorhanden")
            return {'CANCELLED'}

        if not clip.use_proxy:
            print("Proxy für Tracking aktivieren…")
            bpy.ops.clip.toggle_proxy()

        scene = context.scene
        current_frame = scene.frame_current
        print(f"Aktueller Frame: {current_frame}")

        print("Starte Rückwärts-Tracking...")
        bpy.ops.clip.track_markers(backwards=True, sequence=True)
        print("Rückwärts-Tracking abgeschlossen.")

        # Zurück zum ursprünglichen Frame springen
        scene.frame_current = current_frame
        print(f"Zurück zum Ausgangsframe: {current_frame}")

        print("Starte Vorwärts-Tracking...")
        bpy.ops.clip.track_markers(backwards=False, sequence=True)
        print("Vorwärts-Tracking abgeschlossen.")

        # Sicherstellen, dass Frame wieder korrekt gesetzt ist
        scene.frame_current = current_frame
        print(f"Finaler Frame gesetzt auf: {current_frame}")

        return {'FINISHED'}


class TRACK_PT_auto_track_panel(bpy.types.Panel):
    """UI Panel für den bidirektionalen Auto-Track"""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = "Auto Track"

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.auto_track_bidir", icon='TRACKING_FORWARDS')

classes = [
    TRACK_OT_auto_track_bidir,
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
