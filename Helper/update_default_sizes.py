import bpy
import math
from typing import Optional, Tuple

# --- Imports -----------------------------------------------------------------
from .bootstrap import run_bootstrap  # Bootstrap aufrufen, wenn Pattern = _MAX erreicht

# --- Konstante Grenzen -------------------------------------------------------
_MIN, _MAX = 30, 100


# -----------------------------------------------------------------------------
# interne Hilfsfunktionen
# -----------------------------------------------------------------------------
def _clamp(val: int, lo: int = _MIN, hi: int = _MAX) -> int:
    return max(lo, min(hi, int(val)))


def _get_tracking_settings(context: bpy.types.Context) -> Optional[bpy.types.MovieTrackingSettings]:
    """Liefert die MovieTrackingSettings des aktiven Clips (falls vorhanden)."""
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

    scene_clip = getattr(getattr(context, "scene", None), "clip", None)
    if scene_clip and getattr(scene_clip, "tracking", None) and getattr(scene_clip.tracking, "settings", None):
        return scene_clip.tracking.settings

    return None


def compute_new_sizes(old_pattern: int) -> Tuple[int, int]:
    """Berechnet neue Größen, clamped auf [_MIN, _MAX]."""
    new_pattern = _clamp(round(old_pattern * 1.1))
    new_search = (new_pattern * 2)
    return new_pattern, new_search


# -----------------------------------------------------------------------------
# Hauptfunktion
# -----------------------------------------------------------------------------
def update_default_sizes(context: bpy.types.Context) -> Tuple[int, int, int, int]:
    """
    Liest aktuelle Defaults, berechnet neue Werte und schreibt sie zurück.
    Falls new_pattern == _MAX → Bootstrap neu auslösen.
    Returns: (old_pattern, old_search, new_pattern, new_search)
    """
    settings = _get_tracking_settings(context)
    if not settings:
        raise ValueError("[Kaiserlich Tracker] Kein aktiver MovieClip/TrackingSettings gefunden.")

    old_pattern = int(getattr(settings, "default_pattern_size", 0))
    old_search = int(getattr(settings, "default_search_size", 0))

    new_pattern, new_search = compute_new_sizes(old_pattern)

    # Werte setzen
    settings.default_pattern_size = new_pattern
    settings.default_search_size = new_search

    # --- Bootstrap auslösen, wenn Pattern-Max erreicht -----------------------
    if new_pattern >= _MAX:
        scene = getattr(context, "scene", None)
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25)) if scene else 25
        result = run_bootstrap(context, ef_target)

    return old_pattern, old_search, new_pattern, new_search