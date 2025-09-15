import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("run_jump_to_frame", "jump_to_frame")
# jump_to_frame = Legacy-Wrapper
REPEAT_SATURATION = 10  # Ab dieser Wiederholungsanzahl: Optimizer anstoßen statt Detect

# ---------------------------------------------------------------------------
# Fade-/Ring-Parameter
# ---------------------------------------------------------------------------
# Ringbreite = 5 Frames je Seite (Zentralband umfasst damit [f-5 .. f+5]).
FADE_STEP_FRAMES: int = 5


def _fade_step_frames() -> int:
    """Liest den Fade-Step aus Scene-Property (kc_repeat_fade_step) oder nutzt Default."""
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

# ---------------------------------------------------------------------------
# Ring-Expansion nach Spezifikation
# ---------------------------------------------------------------------------
# Kurzlogik:
# - Bei k-ter Wiederholung am Frame f:
#   Ring 0  : [f-5 .. f+5]           → Wert k
#   Ring m≥1: linke/rechte Intervalle → Wert k-m
#             L: [f-5*(m+1) .. f-(5*m+1)]
#             R: [f+(5*m+1) .. f+5*(m+1)]
# - Pro Frame: MAX-Merge, Clamping auf Scene-Range.

def _write_max(mapping: Dict[int, int], i: int, v: int) -> None:
    cur = mapping.get(i, 0)
    if v > cur:
        mapping[i] = v


def _expand_repeat_series_for_jump(
    *, center_f: int, repeat_count: int, lo: int, hi: int, step: int
) -> Dict[int, int]:
    """
    Baut ein lokales Mapping {frame: value} für die k-te Wiederholung am Ziel-Frame.
    Exakte Ring-Definition gemäß Spezifikation, inklusive Clamping und MAX-Merge.
    """
    out: Dict[int, int] = {}
    k = int(repeat_count)
    if k <= 0:
        return out

    # Ring 0: [f-step .. f+step] → k
    start0 = max(lo, center_f - step)
    end0 = min(hi, center_f + step)
    for i in range(start0, end0 + 1):
        _write_max(out, i, k)

    # Ringe 1..k-1: Wert (k-m) mit 5er-Ringbreite je Seite
    for m in range(1, k):
        val = k - m
        # Links: [f-5*(m+1) .. f-(5*m+1)]
        L1 = max(lo, center_f - step * (m + 1))
        L2 = max(lo, center_f - (step * m + 1))
        if L1 <= L2:
            for i in range(L1, L2 + 1):
                _write_max(out, i, val)
        # Rechts: [f+(5*m+1) .. f+5*(m+1)]
        R1 = min(hi, center_f + (step * m + 1))
        R2 = min(hi, center_f + step * (m + 1))
        if R1 <= R2:
            for i in range(R1, R2 + 1):
                _write_max(out, i, val)
    return out


def _spread_repeat_to_neighbors(repeat_map: dict[int, int], center_f: int, radius: int, base: int) -> None:
    """
    (Legacy-Helfer, weiterhin kompatibel)
    Erzeugt stufigen Fade basierend auf 'radius' und 'base' – ohne Clamping.
    Hinweis: Für exakte Ringspezifikation wird _expand_repeat_series_for_jump() genutzt.
    """
    step = _fade_step_frames()
    for off in range(-radius, radius + 1):
        f = center_f + off
        if f < 0:
            continue
        # Legacy-Approx; belassen für Rückwärtskompatibilität
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
    repeat_map: Optional[Dict[int, int]] = None,  # (Kompat): wird nicht mehr genutzt
) -> Dict[str, Any]:
    """
    Setzt den Playhead deterministisch auf 'frame' (oder scene['goto_frame']).
    - Clamped auf Clipgrenzen
    - Optionaler CLIP_EDITOR-Override & Modus-Setzung
    - Wiederholungszählung & Ring-Expansion erfolgen über tracking_state.orchestrate_on_jump

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

    # Einheitlicher Zähler & Ringe zentral aktualisieren (SSOT)
    try:
        from .tracking_state import orchestrate_on_jump
        orchestrate_on_jump(context, int(target))
    except Exception as e:  # noqa: BLE001
        print(f"[JumpTo][WARN] orchestrate_on_jump failed: {e!r}")

    # Logging NACH SSOT-Update: konsistenten Wert lesen
    repeat_count = 0
    try:
        from .properties import get_repeat_value
        step = int(getattr(scn, "kc_repeat_fade_step", 5))
        k_used = int(get_repeat_value(scn, int(target)))
        repeat_count = k_used
        print(f"[JumpTo][Count] frame={int(target)} repeat={k_used} (SSOT)")
        fs, fe = int(scn.frame_start), int(scn.frame_end)
        left = max(fs, int(target) - k_used * step)
        right = min(fe, int(target) + k_used * step)
        print(f"[JumpTo][Spread] rings={k_used} step={step} outer_radius={k_used*step} bounds≈{left}..{right}")
    except Exception:  # noqa: BLE001
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
