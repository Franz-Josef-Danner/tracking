import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")  # jump_to_frame = Legacy-Wrapper


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
    - Clamped auf Clipgrenzen
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
        print("[GotoFrame] Kein MovieClip im Kontext.")
        return {"status": "FAILED", "reason": "no_clip", "frame": None, "repeat_count": 0, "clamped": False, "area_switched": False}

    # Ziel-Frame bestimmen
    target = frame
    if target is None:
        target = scn.get("goto_frame", None)
    if target is None:
        print("[GotoFrame] Scene-Variable 'goto_frame' nicht gesetzt.")
        return {"status": "FAILED", "reason": "no_target", "frame": None, "repeat_count": 0, "clamped": False, "area_switched": False}

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
                    scn.frame_current = target
            except Exception:
                # Fallback: ohne Override setzen
                scn.frame_current = target
        else:
            # Kein CLIP_EDITOR sichtbar → trotzdem setzen
            scn.frame_current = target
    else:
        scn.frame_current = target
    # Besuchszählung je Ziel-Frame (1=erster Besuch, 2=erste Wiederholung, ...)
    repeat_count = 1
    if repeat_map is not None:
        repeat_count = int(repeat_map.get(target, 0)) + 1
        repeat_map[target] = repeat_count
    
    # optional: wenn du nur eine Logzeile möchtest, kannst du diese entfernen
    # ------------------------------------------------------------------
    # REPEAT-HOOK: Bei Wiederholung (Frame wurde schon einmal per Jump angefahren)
    # → Nur noch marker_helper_main() ausführen.
    # ------------------------------------------------------------------
    if repeat_count >= 2:
        # robust importieren (Package vs. Flat)
        try:
            from ..Helper.marker_helper_main import marker_helper_main
        except Exception:
            from Helper.marker_helper_main import marker_helper_main  # type: ignore
        try:
            marker_helper_main(context)
            print(f"[JumpRepeat] marker_helper_main ausgelöst (frame={target}, repeat={repeat_count})")
        except Exception as ex:
            print(f"[JumpRepeat] marker_helper_main Fehler: {ex}")

    # Debugging & Transparenz
    try:
        scn["last_jump_frame"] = int(target)  # rein informativ; orchestrator nutzt repeat_map intern
    except Exception:
        pass

    print(f"[GotoFrame] Playhead auf Frame {target} gesetzt. (clamped={clamped}, repeat={repeat_count})")
    return {"status": "OK", "frame": int(target), "repeat_count": int(repeat_count), "clamped": bool(clamped), "area_switched": bool(area_switched)}


# -----------------------------------------------------------------------------
# Legacy-Wrapper (Kompatibilität)
# -----------------------------------------------------------------------------

def jump_to_frame(context):
    """
    Kompatibel zur alten Signatur:
      - liest 'scene[\"goto_frame\"]'
      - ruft run_jump_to_frame()
      - gibt bool zurück (True bei OK)
    """
    res = run_jump_to_frame(context, frame=None, repeat_map=None)
    ok = (res.get("status") == "OK")
    if ok:
        print(f"[GotoFrame] Legacy OK → Frame {res.get('frame')}")
    else:
        print(f"[GotoFrame] Legacy FAILED → {res.get('reason','')}")
    return ok
