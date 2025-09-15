import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")
# jump_to_frame = Legacy-Wrapper
REPEAT_SATURATION = 10  # Ab dieser Wiederholungsanzahl: Optimizer anstoßen statt Detect

# ---------------------------------------------------------------------------
# Fade-Parameter
# ---------------------------------------------------------------------------
# Statt "pro Frame -1" wird nur alle N Frames um 1 dekrementiert.
# Damit entsteht ein Plateau von N Frames pro Stufe.
FADE_STEP_FRAMES: int = 5


def _fade_step_frames() -> int:
    """Liest den stufigen Fade-Step aus der Scene-Property (Fallback auf Default)."""
    try:
        scn = bpy.context.scene
        val = int(getattr(scn, "kc_repeat_fade_step", FADE_STEP_FRAMES))
        return max(1, val)
    except Exception:
        return FADE_STEP_FRAMES


def _dbg_enabled(scn) -> bool:
    try:
        return bool(getattr(scn, "kc_debug_repeat", True))
    except Exception:
        return True


def _dbg(scn, msg: str) -> None:
    if _dbg_enabled(scn):
        try:
            print(msg)
        except Exception:
            pass


def _clamp(v: int, lo: int = 0, hi: int | None = None) -> int:
    if hi is None:
        return v if v >= lo else lo
    return lo if v < lo else (hi if v > hi else v)


def _spread_repeat_to_neighbors(repeat_map: dict[int, int], center_f: int, radius: int, base: int) -> None:
    """Stufiger Fade-Out um 'center_f' mit MAX-Merge in das lokale Mapping."""
    step = _fade_step_frames()
    for off in range(-radius, radius + 1):
        f = center_f + off
        if f < 0:
            continue
        # Decrement stufig: 0..(step-1) → 0, step..(2*step-1) → 1, ...
        dec = abs(off) // step
        v = base - dec
        if v <= 0:
            continue
        if v > repeat_map.get(f, 0):
            repeat_map[f] = v


def diffuse_repeat_counts(repeat_map: dict[int, int], radius: int) -> dict[int, int]:
    """
    Breitet Wiederholungszähler auf Nachbarframes aus, mit stufigem Fade
    (alle FADE_STEP_FRAMES Frames -1).
    """
    if not repeat_map or radius <= 0:
        return repeat_map
    out = dict(repeat_map)
    for center_f, base in repeat_map.items():
        _spread_repeat_to_neighbors(out, center_f, radius, base)
    return out


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
        return {"status": "FAILED", "reason": "no_clip", "frame": None, "repeat_count": 0, "clamped": False, "area_switched": False}

    # Ziel-Frame bestimmen
    target = frame
    if target is None:
        target = scn.get("goto_frame", None)
    if target is None:
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
    _dbg(scn, f"[JumpTo] target={target} clamped={clamped} ui_override={use_ui_override}")

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

    # Besuchszählung je Ziel-Frame
    repeat_count = 1
    if repeat_map is not None:
        repeat_count = int(repeat_map.get(target, 0)) + 1
        repeat_map[target] = repeat_count
    _dbg(scn, f"[JumpTo][Count] frame={int(target)} repeat={int(repeat_count)}")

    # Diffusion nur lokal um den aktuellen Jump, dann Bulk-Merge (verhindert Flackern)
    step = _fade_step_frames()
    radius = max(0, repeat_count * step - 1)
    expanded = {int(target): int(repeat_count)}
    _spread_repeat_to_neighbors(expanded, int(target), radius, int(repeat_count))
    if len(expanded) > 1:
        keys = sorted(expanded.keys())
        _dbg(scn, f"[JumpTo][Spread] radius={radius} step={step} write_frames={len(expanded)} range={keys[0]}..{keys[-1]}")
    try:
        # lazy import & Bulk-Write
        from .properties import record_repeat_bulk_map
        record_repeat_bulk_map(scn, expanded)
    except Exception as e:
        _dbg(scn, f"[JumpTo][WARN] bulk write failed: {e!r}")
        # Fallback: Einzelwert (minimal)
        try:
            from .properties import record_repeat_count
            record_repeat_count(scn, int(target), int(repeat_count))
        except Exception as e2:
            _dbg(scn, f"[JumpTo][ERR] single write failed: {e2!r}")

    # Diagnose: Serienstatus nach Merge
    try:
        series = scn.get("_kc_repeat_series") or []
        nz = sum(1 for v in series if v)
        fs, fe = int(scn.frame_start), int(scn.frame_end)
        expected = max(0, fe - fs + 1)
        _dbg(scn, f"[JumpTo][Series] len={len(series)} expected={expected} nonzero={nz}")
    except Exception:
        pass

    # Debugging & Transparenz
    try:
        scn["last_jump_frame"] = int(target)  # rein informativ
    except Exception:
        pass

    # Sättigungsflag für Rückgabe/Logging
    repeat_saturated = repeat_count >= REPEAT_SATURATION
    if repeat_saturated:
        _dbg(scn, f"[JumpTo][Repeat] saturated >= {REPEAT_SATURATION} at frame={int(target)} (repeat={int(repeat_count)})")

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
