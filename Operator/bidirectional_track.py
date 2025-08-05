import bpy

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Track Bidirectional and Filter Short Tracks"
    bl_description = "Track selektierte Marker bidirektional und lösche kurze Tracks"

    def execute(self, context):
        scene = context.scene
        min_length = scene.frames_track if hasattr(scene, "frames_track") else 5

        area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
        if not area:
            self.report({'ERROR'}, "Clip Editor nicht gefunden.")
            return {'CANCELLED'}

        # Track bidirectional
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

        # Track-Längen prüfen
        deleted_any = False
        for track in context.space_data.clip.tracking.tracks:
            if track.select:
                # Längen zählen
                frame_numbers = [p.co[0] for p in track.markers if not p.mute]
                if frame_numbers:
                    track_length = len(set(frame_numbers))
                    if track_length < min_length:
                        track.select = True
                        deleted_any = True
                    else:
                        track.select = False

        # Kurze löschen
        if deleted_any:
            bpy.ops.clip.delete_track()
            self.report({'INFO'}, "Kurze Tracks wurden gelöscht.")
        else:
            self.report({'INFO'}, "Keine zu kurzen Tracks gefunden.")

        return {'FINISHED'}
