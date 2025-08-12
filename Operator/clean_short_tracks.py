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
    
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "Kein Clip im CLIP_EDITOR Kontext gefunden")
            return {'CANCELLED'}
    
        tracks = clip.tracking.tracks
    
        # Nur wenn wirklich Tracks gelöscht werden sollen
        if self.action == 'DELETE_TRACK':
            # Pre-Pass: leere oder vollständig gemutete Tracks löschen
            to_delete = [t for t in tracks
                         if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)]
            if to_delete:
                for t in tracks:
                    t.select = False
                for t in to_delete:
                    t.select = True
                bpy.ops.clip.delete_track()
    
        # Frames defensiv auf >= 1 setzen
        frames = max(int(scene.frames_track), 1)
    
        # Dein bestehender Clean-Call (unverändert)
        bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=self.action)
    
        # Post-Pass: nach dem Cleanen neu entstandene Hüllen entfernen
        if self.action == 'DELETE_TRACK':
            tracks = clip.tracking.tracks  # refresh
            to_delete = [t for t in tracks
                         if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)]
            if to_delete:
                for t in tracks:
                    t.select = False
                for t in to_delete:
                    t.select = True
                bpy.ops.clip.delete_track()
    
        self.report({'INFO'}, f"Tracks < {frames} Frames wurden bearbeitet. Aktion: {self.action}")
        return {'FINISHED'}

