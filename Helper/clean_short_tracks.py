# Helper/clean_short_tracks.py — echter Short-Track-Cleaner NACH dem Tracking.
# Respektiert Gate-Flags aus Detect, schützt frische Namen und sanitizt Strings.

import bpy

__all__ = ("clean_short_tracks",)

_LOCK_KEY = "__detect_lock"


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
                        "scene": context.scene,
                    }
    return None


def _resolve_clip(context):
    """Clip robust bestimmen: bevorzugt aktiver CLIP_EDITOR, sonst Fallback auf erstes MovieClip."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


def _coerce_utf8_str(x):
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        for enc in ("utf-8", "latin-1"):
            try:
                return b.decode(enc).strip()
            except Exception:
                pass
        return None
    try:
        s = str(x).strip()
        return s or None
    except Exception:
        return None


def _coerce_utf8_str_list(seq):
    return [s for s in (_coerce_utf8_str(x) for x in (seq or [])) if s]


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


def clean_short_tracks(context, *, frames: int = None, action: str = 'DELETE_TRACK'):
    """
    Löscht/selektiert Tracks mit weniger Frames als 'frames'.
    Respektiert:
      - scene["pipeline_do_not_start"]
      - scene["__skip_clean_short_once"] (One-Shot)
      - scene["__just_created_names"] (Schutzliste, UTF-8-sanitized)
    """
    scene = context.scene

    # Gate: Pipeline darf jetzt nicht starten
    if scene.get("pipeline_do_not_start", False):
        print("[CleanShort] blocked by pipeline_do_not_start")
        return {'CANCELLED'}

    # One-shot Skip direkt nach READY
    if scene.get("__skip_clean_short_once"):
        print("[CleanShort] skipped once to protect fresh detects")
        scene["__skip_clean_short_once"] = False
        return {'CANCELLED'}

    # Frames ermitteln (Default: scene.frames_track)
    if frames is None:
        if not hasattr(scene, "frames_track"):
            print("[CleanShort] Fehler: Scene.frames_track nicht definiert")
            return {'CANCELLED'}
        frames = int(scene.frames_track)
    frames = max(int(frames), 1)

    clip = _resolve_clip(context)
    if clip is None:
        print("[CleanShort] Fehler: Kein MovieClip verfügbar / kein CLIP_EDITOR Kontext gefunden")
        return {'CANCELLED'}

    override = _clip_override(context)
    tracks = clip.tracking.tracks

    # Frische Namen schützen (Sanitizing!)
    fresh_raw = scene.get("__just_created_names", []) or []
    fresh = set(_coerce_utf8_str_list(fresh_raw))
    if fresh_raw and (len(fresh) != len(fresh_raw)):
        print("[CleanShort] normalized __just_created_names")

    # Pre-Pass: leere oder vollständig gemutete Tracks löschen
    if action == 'DELETE_TRACK':
        to_delete = [
            t for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            _delete_selected_tracks_with_override(override)

    # Clean: alle selektieren, frische abwählen
    for t in tracks:
        t.select = True
    if fresh:
        for t in tracks:
            if t.name in fresh:
                t.select = False

    # Clean ausführen
    try:
        _clean_tracks_with_override(override, frames=frames, action=action)
    except Exception as ex:
        print("[CleanShort] clean_tracks failed:", ex)
        return {'CANCELLED'}

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
            _delete_selected_tracks_with_override(override)

    # Frischliste leeren (Schutz nur einmal nötig)
    if fresh:
        try:
            scene["__just_created_names"] = []
        except Exception:
            pass

    print(f"[CleanShort] Tracks < {int(frames)} Frames wurden bearbeitet. Aktion: {action}")
    return {'FINISHED'}
