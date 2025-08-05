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
        def run(self):
        print(f"[Tracking] Schritt: {self.step}")
        if self.step == 0:
            print("→ Starte Vorwärts-Tracking...")
            invoke_clip_operator_safely("track_markers", backwards=False, sequence=True)
            self.step = 1
        elif self.step == 1:
            print("→ Warte auf Abschluss des Vorwärts-Trackings...")
            if self.is_tracking_done_robust():
                print("✓ Vorwärts-Tracking abgeschlossen.")
                self.context.scene.frame_current = self.initial_frame  # Frame zurücksetzen
                print(f"← Frame zurückgesetzt auf {self.initial_frame}")
                self.step = 2
        elif self.step == 2:
            print("→ Starte Rückwärts-Tracking...")
            invoke_clip_operator_safely("track_markers", backwards=True, sequence=True)
            self.step = 3
        elif self.step == 3:
            print("→ Warte auf Abschluss des Rückwärts-Trackings...")
            if self.is_tracking_done_robust():
                print("✓ Rückwärts-Tracking abgeschlossen.")
                self.step = 4
        elif self.step == 4:
            print("→ Starte Bereinigung kurzer Tracks...")
            self.cleanup_short_tracks()
            print("✓ Tracking und Cleanup abgeschlossen.")
            return None
        return 0.5

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
