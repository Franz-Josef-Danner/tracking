import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")  # jump_to_frame = Legacy-Wrapper
REPEAT_SATURATION = 10  # Ab dieser Wiederholungsanzahl: Optimizer anstoßen statt Detect


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _resolve_clip_and_scene(context, clip=None, scene=None) -> Tuple[Optional[bpy.types.MovieClip], bpy.types.Scene]:
    scn = scene or context.scene
    if clip is not None:
        return clip, scn

    # 1) Aktiver CLIP_EDITOR
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == 'CLIP_EDITOR':
        c = getattr(space, "clip", None)
        if c:
            return c, scn

    # 2) Fallback: irgendein vorhandener Clip
    for c in bpy.data.movieclips:
        return c, scn

    return None, scn


def _clip_bounds(clip: bpy.types.MovieClip) -> Tuple[int, int]:
    """Roh-Bounds des Clips (ohne Szene-Intersection)."""
    try:
        start = int(clip.frame_start)
        dur = int(getattr(clip, "frame_duration", 0))
        end = start + max(0, dur - 1)
    except Exception:
        start = int(clip.frame_start) if hasattr(clip, "frame_start") else 1
        end = start
    return start, end


def _find_clip_area(win) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region]]:
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
    repeat_map: Optional[Dict[int, int]] = None,  # Operator-interne Wiederholungszählung
) -> Dict[str, Any]:
    """
    Setzt den Playhead deterministisch auf 'frame' (oder scene['goto_frame']).
    - Clamped auf Schnittmenge Szene × Clip
    - Optionaler CLIP_EDITOR-Override & Modus-Setzung
    - Zählt Wiederholungen NUR für per Jump gesetzte Frames via repeat_map

    Returns:
      {"status": "OK"|"FAILED",
       "frame": int,
       "repeat_count": int,
       "clamped": bool,
       "area_switched": bool}
    """
    scn = context.scene
    clip, scn = _resolve_clip_and_scene(context)
    if ensure_clip and not clip:
        return {"status": "FAILED", "reason": "no_clip", "frame": None, "repeat_count": 0, "clamped": False, "area_switched": False}

    # Ziel-Frame bestimmen
    target = frame
    if target is None:
        target = scn.get("goto_frame", None)
    if target is None:
        return {"status": "FAILED", "reason": "no_target", "frame": None, "repeat_count": 0, "clamped": False, "area_switched": False}

    target = int(target)

    # Clamp auf Schnittmenge Szene × Clip (falls Clip vorhanden)
    clamped = False
    if clip:
        clip_lo, clip_hi = _clip_bounds(clip)
        scene_lo, scene_hi = int(scn.frame_start), int(scn.frame_end)
        start = max(scene_lo, clip_lo)
        end = min(scene_hi, clip_hi)
    else:
        start = int(scn.frame_start)
        end = int(scn.frame_end)

    if target < start:
        target = start
        clamped = True
    elif target > end:
        target = end
        clamped = True

    # Optional: UI-Override (Area/Region) & Tracking-Mode
    area_switched = False
    if use_ui_override:
        area, region = _find_clip_area(getattr(context, "window", None))
        if area and region:
            try:
                with context.temp_override(area=area, region=region, space_data=area.spaces.active):
                    if ensure_tracking_mode:
                        try:
                            sd = area.spaces.active
                            if hasattr(sd, "mode") and sd.mode != 'TRACKING':
                                sd.mode = 'TRACKING'
                                area_switched = True
                        except Exception:
                            pass
                    scn.frame_set(target)
            except Exception:
                # Fallback: ohne Override setzen
                scn.frame_set(target)
        else:
            # Kein CLIP_EDITOR sichtbar → trotzdem setzen
            scn.frame_set(target)
    else:
        scn.frame_set(target)

    # Besuchszählung je Ziel-Frame
    repeat_count = 1
    if repeat_map is not None:
        repeat_count = int(repeat_map.get(target, 0)) + 1
        repeat_map[target] = repeat_count

    # Debugging & Transparenz
    try:
        scn["last_jump_frame"] = int(target)  # rein informativ
    except Exception:
        pass

    # Sättigungsflag für Rückgabe/Logging
    repeat_saturated = repeat_count >= REPEAT_SATURATION

    return {
        "status": "OK",
        "frame": int(target),
        "repeat_count": int(repeat_count),
        "repeat_saturated": bool(repeat_saturated),
        "clamped": bool(clamped),
        "area_switched": bool(area_switched),
    }


# -----------------------------------------------------------------------------
# Legacy-Wrapper (Kompatibilität)
# -----------------------------------------------------------------------------

def jump_to_frame(context):
    """
    Kompatibel zur alten Signatur:
      - liest 'scene["goto_frame"]'
      - ruft run_jump_to_frame()
      - gibt bool zurück (True bei OK)
    """
    res = run_jump_to_frame(context, frame=None, repeat_map=None)
    ok = (res.get("status") == "OK")
    return ok
