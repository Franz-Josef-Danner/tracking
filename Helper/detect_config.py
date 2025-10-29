import bpy
import math

def get_detect_params(context: bpy.types.Context) -> dict:
    """Liest Clip-bezogene Detect-Parameter aus und berechnet initiale Defaults."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        raise RuntimeError("Kein aktiver MovieClip verfügbar.")
    
    tracking_settings = getattr(clip.tracking, "settings", None)
    hz, vc = clip.size if getattr(clip, "size", None) else (1920, 1080)

    margin       = getattr(tracking_settings, "margin", 100)
    pattern_size = getattr(tracking_settings, "pattern_size", 50)
    search_size  = getattr(tracking_settings, "search_size", 100)
    threshold    = 0.0001
    min_distance = hz * 0.025

    return {
        "hz": hz,
        "vc": vc,
        "margin": margin,
        "pattern_size": pattern_size,
        "search_size": search_size,
        "threshold": threshold,
        "min_distance": min_distance
    }


def adjust_min_distance(last_md: float, target: int, found: int) -> float:
    """Passt den min_distance-Wert adaptiv an, basierend auf Ziel- vs. Ist-Markerzahl."""
    if found <= 0:
        return last_md * 1.5
    ratio = target / found
    factor = max(0.5, min(2.0, ratio))
    return max(1.0, last_md / factor)
