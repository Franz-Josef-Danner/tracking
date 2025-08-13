import bpy

__all__ = ("clean_short_tracks",)


def clean_short_tracks(context, action='DELETE_TRACK'):
    """
    Löscht oder selektiert Tracks mit weniger Frames als 'frames_track'.
    :param context: Blender-Kontext
    :param action: 'SELECT', 'DELETE_TRACK', 'DELETE_SEGMENTS'
    """
    scene = context.scene
    if not hasattr(scene, "frames_track"):
        print("[CleanShortTracks] Fehler: Scene.frames_track nicht definiert")
        return {'CANCELLED'}

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[CleanShortTracks] Fehler: Kein Clip im CLIP_EDITOR Kontext gefunden")
        return {'CANCELLED'}

    tracks = clip.tracking.tracks

    # Nur wenn wirklich Tracks gelöscht werden sollen
    if action == 'DELETE_TRACK':
        # Pre-Pass: leere oder vollständig gemutete Tracks löschen
        to_delete = [
            t for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            bpy.ops.clip.delete_track()

    # Frames defensiv auf >= 1 setzen
    frames = max(int(scene.frames_track), 1)

    # Bestehender Clean-Call (unverändert)
    bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=action)

    # Post-Pass: nach dem Cleanen neu entstandene Hüllen entfernen
    if action == 'DELETE_TRACK':
        tracks = clip.tracking.tracks  # refresh
        to_delete = [
            t for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            bpy.ops.clip.delete_track()

    print(f"[CleanShortTracks] Tracks < {frames} Frames wurden bearbeitet. Aktion: {action}")
    return {'FINISHED'}
