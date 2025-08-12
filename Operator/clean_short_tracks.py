def execute(self, context):
    scene = context.scene
    if not hasattr(scene, "frames_track"):
        self.report({'ERROR'}, "Scene.frames_track nicht definiert")
        return {'CANCELLED'}

    clip = context.space_data.clip
    tracks = clip.tracking.tracks

    # PRE-PASS: Nur wenn wirklich Tracks gelöscht werden sollen
    if self.action == 'DELETE_TRACK':
        # leere oder vollständig gemutete Tracks sammeln
        empty_or_all_muted = [t for t in tracks
                              if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)]
        if empty_or_all_muted:
            # Selektionsbasiertes Löschen per Operator (API-sicher)
            for t in tracks:
                t.select = False
            for t in empty_or_all_muted:
                t.select = True
            bpy.ops.clip.delete_track()

    # frames defensiv auf >= 1 setzen (sonst erwischt der Operator keine leeren Hüllen)
    frames = max(int(scene.frames_track), 1)

    # dein bestehender Aufruf – unverändert
    bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=self.action)

    # POST-PASS: wieder nur bei echter Track-Löschaktion
    if self.action == 'DELETE_TRACK':
        tracks = clip.tracking.tracks  # Refresh nach Operator
        empty_or_all_muted = [t for t in tracks
                              if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)]
        if empty_or_all_muted:
            for t in tracks:
                t.select = False
            for t in empty_or_all_muted:
                t.select = True
            bpy.ops.clip.delete_track()

    self.report({'INFO'}, f"Tracks < {frames} Frames bearbeitet. Aktion: {self.action}")
    return {'FINISHED'}
