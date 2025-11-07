# Helper/update_default_sizes.py
# Setzt default_pattern_size := round(old * 1.1) (geclamped [5..1000])
# und default_search_size := pattern * 2 (ebenfalls geclamped [5..1000])

import bpy
from typing import Optional, Tuple

_MIN, _MAX = 30, 100

def _clamp(val: int, lo: int = _MIN, hi: int = _MAX) -> int:
    return max(lo, min(hi, int(val)))

def _get_tracking_settings(context: bpy.types.Context) -> Optional[bpy.types.MovieTrackingSettings]:
    """
    Liefert die MovieTrackingSettings des aktiven Clips (falls vorhanden).
    Greift bevorzugt auf den im Clip-Editor aktiven Clip zu, fallback: space_data.clip.
    """
    # 1) Versuche aktiven Clip aus dem Clip-Editor
    area_clip = None
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for space in area.spaces:
                if space.type == 'CLIP_EDITOR' and space.clip:
                    area_clip = space.clip
                    break
        if area_clip:
            break

    clip = area_clip or getattr(getattr(context, "space_data", None), "clip", None)
    if clip and getattr(clip, "tracking", None) and getattr(clip.tracking, "settings", None):
        return clip.tracking.settings

    # 2) Fallback: aktiver Clip über Szene (falls verfügbar)
    scene_clip = getattr(getattr(context, "scene", None), "clip", None)
    if scene_clip and getattr(scene_clip, "tracking", None) and getattr(scene_clip.tracking, "settings", None):
        return scene_clip.tracking.settings

    return None

def compute_new_sizes(old_pattern: int) -> Tuple[int, int]:
    """
    Rechnet neue Größen:
    - new_pattern = clamp(round(old_pattern * 1.1))
    - new_search  = clamp(new_pattern * 2)
    """
    new_pattern = _clamp(round(old_pattern * 1.1))
    new_search = (new_pattern * 2)
    return new_pattern, new_search

def update_default_sizes(context: bpy.types.Context) -> Tuple[int, int, int, int]:
    """
    Liest aktuelle Defaults, berechnet neue Werte und schreibt sie zurück.
    Returns: (old_pattern, old_search, new_pattern, new_search)
    Raises: ValueError bei fehlenden Tracking-Settings.
    """
    settings = _get_tracking_settings(context)
    if not settings:
        raise ValueError("[Kaiserlich Tracker] Kein aktiver MovieClip/TrackingSettings gefunden.")

    old_pattern = int(getattr(settings, "default_pattern_size", 0))
    old_search  = int(getattr(settings, "default_search_size", 0))

    new_pattern, new_search = compute_new_sizes(old_pattern)

    settings.default_pattern_size = new_pattern
    settings.default_search_size  = new_search

    return old_pattern, old_search, new_pattern, new_search
