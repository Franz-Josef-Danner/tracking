# Helper/clean_short_tracks.py
import bpy

__all__ = ("clean_short_tracks",)


def _clip_override(context):
    """Sicheren CLIP_EDITOR-Override bereitstellen (oder None)."""
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {
                        "window": win,
                        "screen": win.screen,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }
    return None


def _resolve_clip(context):
    """Clip robust bestimmen: bevorzugt aktiver CLIP_EDITOR, sonst Fallback auf erstes MovieClip."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    # Fallback: erster Clip im File (keine UI-Annahme)
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


def _delete_selected_tracks_with_override(override):
    """Selektierte Tracks löschen, optional mit UI-Override."""
    if override:
        with bpy.context.temp_override(**override):
            bpy.ops.clip.delete_track()
    else:
        bpy.ops.clip.delete_track()


def _clean_tracks_with_override(override, *, frames: int, action: str):
    """Clean-Call, optional mit UI-Override."""
    if override:
        with bpy.context.temp_override(**override):
            bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=action)
    else:
        bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=action)


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

    clip = _resolve_clip(context)
    if clip is None:
        print("[CleanShortTracks] Fehler: Kein MovieClip verfügbar / kein CLIP_EDITOR Kontext gefunden")
        return {'CANCELLED'}

    override = _clip_override(context)
    tracks = clip.tracking.tracks

    # Nur wenn wirklich Tracks gelöscht werden sollen
    if action == 'DELETE_TRACK':
        # Pre-Pass: leere oder vollständig gemutete Tracks löschen
        to_delete = [
            t for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            # Selektion sauber setzen
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            _delete_selected_tracks_with_override(override)

    # Frames defensiv auf >= 1 setzen
    frames = max(int(scene.frames_track), 1)

    # Bestehender Clean-Call (unverändert), aber UI-sicher
    _clean_tracks_with_override(override, frames=frames, action=action)

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
