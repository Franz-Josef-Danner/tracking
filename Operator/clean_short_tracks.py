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

    @classmethod
    def poll(cls, context):
        return (
            context.area and context.area.type == "CLIP_EDITOR" and
            getattr(context.space_data, "clip", None)
        )

    def _prune_empty_and_all_muted(self, clip):
        tracks = clip.tracking.tracks
        removed = 0
        for t in list(tracks):
            # 1) keine Marker ⇒ Container löschen
            if not t.markers:
                tracks.remove(t); removed += 1
                continue
            # 2) alle Marker gemutet ⇒ optional löschen (praktisch bei Segment-Splits)
            if all(getattr(m, "mute", False) for m in t.markers):
                tracks.remove(t); removed += 1
        return removed

    def execute(self, context):
        scene = context.scene
        if not hasattr(scene, "frames_track"):
            self.report({'ERROR'}, "Scene.frames_track nicht definiert")
            return {'CANCELLED'}

        clip = context.space_data.clip
        # Pre-Pass: leere/„nur-mute“-Tracks wegräumen
        self._prune_empty_and_all_muted(clip)

        # frames defensiv auf >=1 setzen, sonst bleiben leere Tracks drin
        frames = max(int(scene.frames_track), 1)

        # Operator: kurze Tracks selektieren/löschen/Segmentbereinigung
        bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=self.action)

        # Post-Pass: Reste wegräumen (Operator kann Hüllen zurücklassen)
        self._prune_empty_and_all_muted(clip)

        self.report({'INFO'}, f"Tracks < {frames} Frames wurden bearbeitet. Aktion: {self.action}")
        return {'FINISHED'}
