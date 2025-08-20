import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")  # jump_to_frame = Legacy-Wrapper

# Ab wie vielen Wiederholungen prüfen wir marker_adapt und signalisieren ggf. den Optimizer
REPEAT_CHECK_THRESHOLD: int = 5
# Obergrenze/Schutzkappe: ab dieser Wiederholungsanzahl könnte der Orchestrator sowieso alternative Pfade fahren
REPEAT_SATURATION: int = 10
# Scene-Key, über den wir den Operator (tracking_coordinator) benachrichtigen
OPTIMIZE_SIGNAL_KEY: str = "__optimize_request"
OPTIMIZE_SIGNAL_VAL: str = "JUMP_REPEAT"
OPTIMIZE_FRAME_KEY: str = "__optimize_frame"


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


def _clip_end(clip: bpy.types.MovieClip, scn: bpy.types.Scene) -> int:
    try:
        start = int(clip.frame_start)
        dur = int(getattr(clip, "frame_duration", 0))
        end = start + max(0, dur - 1)
    except Exception:
        start = int(clip.frame_start) if hasattr(clip, "frame_start") else int(scn.frame_start)
        end = start
    # Szene darf enger sein als Clip
    return min(int(scn.frame_end), end)


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
    - Clamp auf Clipgrenzen
    - Optionaler CLIP_EDITOR-Override & Modus-Setzung
    - Zählt Wiederholungen NUR für per Jump gesetzte Frames via repeat_map

    Erweiterung: Wenn derselbe Frame > REPEAT_CHECK_THRESHOLD mal wiederholt
    angesprungen wurde UND scene["marker_adapt"] > 200 ist, wird ein Signal an den
    Tracking-Koordinator gelegt (scene[OPTIMIZE_SIGNAL_KEY] / scene[OPTIMIZE_FRAME_KEY]).

    Returns:
      {
        "status": "OK"|"FAILED",
        "frame": int | None,
        "repeat_count": int,
        "clamped": bool,
        "area_switched": bool,
        "optimize_signal": bool
      }
    """
    scn = context.scene
    clip, scn = _resolve_clip_and_scene(context)
    if ensure_clip and not clip:
        print("[GotoFrame] Kein MovieClip im Kontext.")
        return {
            "status": "FAILED", "reason": "no_clip", "frame": None,
            "repeat_count": 0, "clamped": False, "area_switched": False,
            "optimize_signal": False,
        }

    # Ziel-Frame bestimmen
    target = frame if frame is not None else scn.get("goto_frame", None)
    if target is None:
        print("[GotoFrame] Scene-Variable 'goto_frame' nicht gesetzt.")
        return {
            "status": "FAILED", "reason": "no_target", "frame": None,
            "repeat_count": 0, "clamped": False, "area_switched": False,
            "optimize_signal": False,
        }
    target = int(target)

    # Clamp an Clipgrenzen
    clamped = False
    if clip:
        start = int(clip.frame_start)
        end = _clip_end(clip, scn)
        if target < start:
            target = start
            clamped = True
        elif target > end:
            target = end
            clamped = True

    # UI-Override / Modus setzen (optional)
    area_switched = False
    if use_ui_override:
        win = context.window
        area, region = _find_clip_area(win)
        if area and region:
            area_switched = True
            with context.temp_override(area=area, region=region, space_data=area.spaces.active):
                if ensure_tracking_mode and hasattr(area.spaces.active, "mode"):
                    try:
                        area.spaces.active.mode = 'TRACKING'
                    except Exception:
                        pass
                scn.frame_set(target)
        else:
            scn.frame_set(target)
    else:
        scn.frame_set(target)

    # Wiederholungszähler
    if repeat_map is not None:
        repeat_map[target] = int(repeat_map.get(target, 0)) + 1
        repeat_count = int(repeat_map[target])
    else:
        repeat_count = 1  # konservativ: erster Besuch

    # --- NEU: Optimizer-Signal nur, wenn >5 Wiederholungen **und** marker_adapt > 200 ---
    optimize_signal = False
    marker_adapt_val = int(scn.get("marker_adapt", 0))
    if repeat_count > int(REPEAT_CHECK_THRESHOLD):
        if marker_adapt_val > 200:
            # Signal an den Orchestrator legen – dieser sollte es im Modal-Tick auswerten
            scn[OPTIMIZE_SIGNAL_KEY] = OPTIMIZE_SIGNAL_VAL
            scn[OPTIMIZE_FRAME_KEY] = int(target)
            optimize_signal = True
            print(
                f"[GotoFrame] Wiederholung>{REPEAT_CHECK_THRESHOLD} (={repeat_count}) und marker_adapt={marker_adapt_val} > 200 → Optimizer-Signal gesetzt."
            )
        else:
            print(
                f"[GotoFrame] Wiederholung>{REPEAT_CHECK_THRESHOLD} (={repeat_count}), aber marker_adapt={marker_adapt_val} ≤ 200 → kein Optimizer-Signal."
            )

    # Soft-Kappe als Zusatzinfo: ab Sättigung könnte der Orchestrator alternative Pfade wählen
    if repeat_count >= REPEAT_SATURATION:
        print(f"[GotoFrame] Repeat-Sättigung erreicht (≥{REPEAT_SATURATION}) am Frame {target}.")

    return {
        "status": "OK",
        "frame": target,
        "repeat_count": repeat_count,
        "clamped": clamped,
        "area_switched": area_switched,
        "optimize_signal": optimize_signal,
    }


# Legacy-Wrapper (Backwards-Compat)

def jump_to_frame(context, frame: Optional[int] = None, repeat_map: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Kompatibler Wrapper, der die neue Logik nutzt."""
    return run_jump_to_frame(
        context,
        frame=frame,
        ensure_clip=True,
        ensure_tracking_mode=True,
        use_ui_override=True,
        repeat_map=repeat_map,
    )
