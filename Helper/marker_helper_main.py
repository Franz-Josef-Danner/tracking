# Helper/marker_helper_main.py
from __future__ import annotations
import bpy
from typing import Tuple, Dict, Any

__all__ = ("marker_helper_main",)

def _resolve_clip(context) -> bpy.types.MovieClip | None:
    """Robustes Clip-Resolving: Scene → Edit-Clip → Space-Clip → erster Clip."""
    scn = context.scene
    clip = getattr(scn, "clip", None)
    if clip:
        return clip
    # Fallbacks
    try:
        clip = getattr(context, "edit_movieclip", None)
        if clip:
            return clip
    except Exception:
        pass
    try:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip:
            return clip
    except Exception:
        pass
    try:
        return next(iter(bpy.data.movieclips), None) if bpy.data.movieclips else None
    except Exception:
        return None


def marker_helper_main(context) -> Tuple[bool, int, Dict[str, Any]]:

    scn = context.scene

    # Source of Truth aus der Szene
    marker_basis   = int(getattr(scn, "marker_frame", 25))     # gewünschte Marker/Frame (UI)
    frames_track   = int(getattr(scn, "frames_track", 25))     # Ziel-Tracklänge (UI)
    resolve_error  = float(getattr(scn, "resolve_error", 2.0)) # Solve-Grenzwert (UI)

    # Ableitungen (klassische Heuristik)
    factor         = int(getattr(scn, "marker_factor", 4))     # optionaler UI-Faktor; Default 4
    marker_adapt   = int(marker_basis * factor)
    marker_min     = int(max(1, round(marker_adapt * 0.9)))
    marker_max     = int(max(2, round(marker_adapt * 1.1)))

    # Bildgröße für margin/min_dist ableiten
    clip = _resolve_clip(context)
    if clip:
        try:
            width, height = getattr(clip, "size", (0, 0))
        except Exception:
            width, height = 0, 0
    else:
        width, height = 0, 0

    margin = max(16, int(0.025 * width))
    min_dist = max(8, int(0.1 * width))

    # Persistenz
    scn["marker_basis"]   = int(marker_basis)   # <- FIND_LOW nutzt diesen Basiswert
    scn["marker_adapt"]   = int(marker_adapt)
    scn["marker_min"]     = int(marker_min)
    scn["marker_max"]     = int(marker_max)
    scn["frames_track"]   = int(frames_track)
    scn["resolve_error"]  = float(resolve_error)
    scn["margin_base"]    = int(margin)
    scn["min_distance_base"] = int(min_dist)
    scn["clip_width"]     = int(width)
    scn["clip_height"]    = int(height)

    # NEU: Detect-Startwerte deterministisch initialisieren.
    # Damit wird jeder Cycle garantiert mit den Baselines (aus Clipgröße) gefahren –
    # und NICHT mit ggf. veralteten tco_* Werten aus einer früheren Session.
    try:
        scn["tco_detect_min_distance"] = float(min_dist)
        scn["kc_min_distance_effective"] = int(min_dist)
        scn["tco_detect_margin"] = int(margin)
    except Exception:
        pass
    # Telemetrie (Konsole): Baselines ausgeben
    try:
        clip_name = getattr(clip, "name", "None")
        print(f"[MarkerHelper] clip='{clip_name}' size={width}x{height} "
              f"→ margin_base={margin}, min_distance_base={min_dist} "
              f"(marker_adapt={marker_adapt}, range={scn['marker_min']}–{scn['marker_max']})")
    except Exception:
        pass
    return True, int(marker_adapt), {"FINISHED"}
