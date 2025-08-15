import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("find_low_marker_frame_core", "run_find_low_marker_frame")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _resolve_clip_and_scene(context, clip=None, scene=None) -> Tuple[Optional[bpy.types.MovieClip], Optional[bpy.types.Scene]]:
    scn = scene or getattr(context, "scene", None)

    if clip is not None:
        return clip, scn

    # 1) Aktiver CLIP_EDITOR
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == 'CLIP_EDITOR':
        c = getattr(space, "clip", None)
        if c:
            return c, scn

    # 2) Fallback: erster existierender MovieClip
    try:
        for c in bpy.data.movieclips:
            return c, scn
    except Exception:
        pass

    return None, scn


def _clip_frame_end(clip: bpy.types.MovieClip, scn: Optional[bpy.types.Scene]) -> int:
    # Harte Clip-Grenze: start + duration - 1
    try:
        c_end = int(clip.frame_start) + int(getattr(clip, "frame_duration", 0)) - 1
        if c_end < int(clip.frame_start):
            c_end = int(clip.frame_start)
    except Exception:
        c_end = int(clip.frame_start)
    # Szene darf enger sein, aber nie weiter als der Clip
    if scn:
        return min(int(scn.frame_end), c_end)
    return c_end

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

# Helper/find_low_marker_frame.py (Ausschnitt: run_find_low_marker_frame)
def run_find_low_marker_frame(
    context,
    *,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Orchestrator-kompatibel:
      - Liefert {"status": "FOUND", "frame": F} | {"status": "NONE"} | {"status":"FAILED","reason":...}
      - Schwellwert: **marker_basis** (nicht marker_min/marker_adapt)
      - Beachtet Clipgrenzen
    """
    try:
        clip, scn = _resolve_clip_and_scene(context)
        if not clip:
            return {"status": "FAILED", "reason": "Kein MovieClip im Kontext."}

        # >>> WICHTIG: BASISWERT verwenden
        marker_basis = int(scn.get("marker_basis", getattr(scn, "marker_frame", 25)))
        if marker_basis < 1:
            marker_basis = 1

        # Frames clampen
        fs = int(frame_start) if frame_start is not None else int(clip.frame_start)
        fe = int(frame_end)   if frame_end   is not None else _clip_frame_end(clip, scn)

        # Logging zeigt jetzt den BASIS-Wert
        frame = find_low_marker_frame_core(
            clip,
            marker_min=int(marker_basis),
            frame_start=fs,
            frame_end=fe,
            exact=True,
            ignore_muted_marker=True,
            ignore_muted_track=True,
        )

        if frame is None:
            return {"status": "NONE"}
        return {"status": "FOUND", "frame": int(frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}


# ---------------------------------------------------------------------------
# Wrapper für den Orchestrator
# ---------------------------------------------------------------------------

def run_find_low_marker_frame(
    context,
    *,
    prefer_adapt: bool = True,
    use_scene_basis: bool = True,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Orchestrator-kompatibel:
      - Liefert {"status": "FOUND", "frame": F} | {"status": "NONE"} | {"status":"FAILED","reason":...}
      - Schwellwertauflösung: marker_min > marker_adapt > marker_basis > 20
      - Beachtet Clipgrenzen
    """
    try:
        clip, scn = _resolve_clip_and_scene(context)
        if not clip:
            return {"status": "FAILED", "reason": "Kein MovieClip im Kontext."}

        # Threshold-Auflösung (Priorität: marker_min > marker_adapt > marker_basis > 20)
        marker_min = None
        if prefer_adapt and scn and ("marker_min" in scn):
            marker_min = int(scn["marker_min"])
        elif prefer_adapt and scn and ("marker_adapt" in scn):
            marker_min = int(scn["marker_adapt"])
        elif use_scene_basis and scn:
            marker_min = int(scn.get("marker_basis", 20))
        else:
            marker_min = 20

        # Frames clampen
        fs = int(frame_start) if frame_start is not None else int(clip.frame_start)
        fe = int(frame_end) if frame_end is not None else _clip_frame_end(clip, scn)

        frame = find_low_marker_frame_core(
            clip,
            marker_min=int(marker_min),
            frame_start=fs,
            frame_end=fe,
            exact=True,
            ignore_muted_marker=True,
            ignore_muted_track=True,
        )

        if frame is None:
            return {"status": "NONE"}
        return {"status": "FOUND", "frame": int(frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}
