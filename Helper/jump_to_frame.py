# Helper/jump_to_frame.py — Original, schlank
import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")  # Legacy-Wrapper bleibt

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _resolve_clip_and_scene(
    context,
    clip=None,
    scene=None
) -> Tuple[Optional[bpy.types.MovieClip], bpy.types.Scene]:
    """Aktiven MovieClip (bevorzugt aus CLIP_EDITOR) + Scene ermitteln."""
    scn = scene or context.scene
    if clip is not None:
        return clip, scn

    # 1) Aktiver CLIP_EDITOR
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == 'CLIP_EDITOR':
        c = getattr(space, "clip", None)
        if c:
            return c, scn

    # 2) Fallback: erster vorhandener Clip
    for c in bpy.data.movieclips:
        return c, scn

    return None, scn


def _clip_end(clip: bpy.types.MovieClip, scn: bpy.types.Scene) -> int:
    """Endframe des Clips (durch Szene ggf. enger)."""
    try:
        start = int(clip.frame_start)
        dur = int(getattr(clip, "frame_duration", 0))
        end = start + max(0, dur - 1)
    except Exception:
        start = int(getattr(clip, "frame_start", scn.frame_start))
        end = start
    return min(int(scn.frame_end), end)


def _find_clip_area(win) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region]]:
    """Ersten CLIP_EDITOR + WINDOW-Region im aktuellen Window finden (für Overrides)."""
    if not win or not getattr(win, "screen", None):
        return None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
            return area, reg
    return None, None


# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------

def run_jump_to_frame(
    context,
    *,
    frame: Optional[int] = None,
    ensure_clip: bool = True,
    ensure_tracking_mode: bool = True,
    use_ui_override: bool = True,
    repeat_map: Optional[Dict[int, int]] = None,  # optional: Wiederholungszählung
) -> Dict[str, Any]:
    """
    Setzt den Playhead deterministisch auf 'frame' (oder scene['goto_frame']).
    - Clamp auf Clipgrenzen
    - Optionaler CLIP_EDITOR-Override & TRACKING-Mode
    - Optional: Zählt Wiederholungen je Ziel-Frame via repeat_map

    Rückgabe:
      {
        "status": "OK"|"FAILED",
        "frame": int,
        "repeat_count": int,
        "clamped": bool,
        "area_switched": bool
      }
    """
    scn = context.scene
    clip, scn = _resolve_clip_and_scene(context)
    if ensure_clip and not clip:
        print("[GotoFrame] Kein MovieClip im Kontext.")
        return {
            "status": "FAILED",
            "reason": "no_clip",
            "frame": None,
            "repeat_count": 0,
            "clamped": False,
            "area_switched":_
