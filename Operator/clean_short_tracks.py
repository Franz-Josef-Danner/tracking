import bpy

class CLIP_OT_clean_short_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_short_tracks"
    bl_label = "Kurze Tracks bereinigen"
    bl_description = "Löscht oder selektiert Tracks mit weniger Frames als 'frames_track'"

    action: bpy.props.EnumProperty(
        name="Aktion",
        items=[
            ('SELECT', "Markieren", "Tracks nur selektieren"),
            ('DELETE_TRACK', "Track löschen", "Tracks mit wenig Frames werden gelöscht"),
            ('DELETE_SEGMENTS', "Segmente löschen", "Nur ungenaue Tracking-Segmente löschen")
        ],
        default='DELETE_TRACK'
    )

    def execute(self, context):
        scene = context.scene
        if not hasattr(scene, "frames_track"):
            self.report({'ERROR'}, "Scene.frames_track nicht definiert")
            return {'CANCELLED'}

        frames = scene.frames_track

        bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=self.action)

        self.report({'INFO'}, f"Tracks < {frames} Frames wurden bearbeitet. Aktion: {self.action}")
        return {'FINISHED'}
