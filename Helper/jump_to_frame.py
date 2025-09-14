import bpy
from typing import Optional, Dict, Any, Tuple

# Hinweis: MAX-Merge ins Overlay erfolgt in Helper/properties.record_repeat_bulk_map()
# Optionaler Hook: Repeat-Werte ins Scope spiegeln (defensiv, kein harter Import)
def _kc_record_repeat(scene, frame, repeat_value):
    try:
        from .properties import record_repeat_count
        record_repeat_count(scene, frame, float(repeat_value))
    except Exception:
        pass

def _kc_record_repeat_bulk_map(scene, repeat_map):
    """Optionaler Bulk-Schreibzugriff ohne harten Import."""
    try:
        from .properties import record_repeat_bulk_map
        record_repeat_bulk_map(scene, repeat_map)
    except Exception:
        # Fallback: Einzelwerte schreiben
        try:
            for f, v in (repeat_map or {}).items():
                _kc_record_repeat(scene, int(f), int(v))
        except Exception:
            pass

__all__ = ("run_jump_to_frame", "jump_to_frame")  # jump_to_frame = Legacy-Wrapper
REPEAT_SATURATION = 10  # Ab dieser Wiederholungsanzahl: Optimizer anstoßen statt Detect

# ---------------------------------------------------------------------------
# Fade-Parameter
# ---------------------------------------------------------------------------
# Statt "pro Frame -1" wird nur alle N Frames um 1 dekrementiert.
# Damit entsteht ein Plateau von N Frames pro Stufe.
FADE_STEP_FRAMES: int = 5  # stufiger Abfall alle 5 Frames

def _fade_step_frames() -> int:
    try:
        val = int(getattr(bpy.context.scene, "kc_repeat_fade_step", FADE_STEP_FRAMES))
        return max(1, val)
    except Exception:
        return FADE_STEP_FRAMES

def _clamp(v: int, lo: int = 0, hi: int | None = None) -> int:
    if hi is None:
        return v if v >= lo else lo
    return lo if v < lo else (hi if v > hi else v)


def _spread_repeat_to_neighbors(repeat_map: dict[int, int], center_f: int, radius: int, base: int) -> None:
    """5-Frame-Stufenabfall um center_f; schreibt NUR ins lokale Mapping (kein Live-Redraw)."""
    # Szenegrenzen sauber clampen
    try:
        scn = bpy.context.scene
        fmin, fmax = int(scn.frame_start), int(scn.frame_end)
    except Exception:
        fmin, fmax = -10**9, 10**9

    if radius < 0:
        radius = 0

    step = _fade_step_frames()
    for off in range(-radius, radius + 1):
        f = center_f + off
        if f < fmin or f > fmax:
            continue
        # Decrement in Stufen gemäß step: 0..(step-1) → 0, step..(2*step-1) → 1, ...
        dec = abs(off) // step
        v = base - dec
        if v <= 0:
            continue
        # Max-Merge: nur anheben
        if v > repeat_map.get(f, 0):
            repeat_map[f] = v


def diffuse_repeat_counts(repeat_map: dict[int, int], radius: int) -> dict[int, int]:
    """Breitet Wiederholungszähler auf Nachbarframes aus, mit stufigem Fade."""
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
    Returns: {"status": "OK"|"FAILED", "frame": int, "repeat_count": int, "clamped": bool, "area_switched": bool}
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
                        except Exception:
                            pass
                    scn.frame_current = target
            except Exception:
                # Fallback: ohne Override setzen
                scn.frame_current = target
            else:
                area_switched = True
        else:
            # Kein CLIP_EDITOR sichtbar → trotzdem setzen
            scn.frame_current = target
    else:
        scn.frame_current = target

    # Erstes Status-Log
    try:
        print(f"[JumpTo] target={target} clamped={clamped} ui_override={use_ui_override}")
    except Exception:  # defensiv
        pass

    # Besuchszählung je Ziel-Frame
    repeat_count = 1
    if repeat_map is not None:
        repeat_count = int(repeat_map.get(target, 0)) + 1
        repeat_map[target] = repeat_count
    else:
        # Fallback: Scene-Map als Quelle, damit Overlay immer aktualisiert wird
        try:
            from .properties import get_repeat_map
            cur = int(get_repeat_map(scn).get(target, 0))
        except Exception:
            cur = 0
        repeat_count = cur + 1
        repeat_map = {int(target): repeat_count}

    # Center-Peak NICHT sofort einzeln schreiben; Bulk-Write vermeidet Flackern.
    # Diffusion NUR um den aktuellen Jump, nicht global.
    step = _fade_step_frames()
    # Plateau je Stufe: 'step' Frames; Radius skaliert mit Repeat-Count
    radius = max(0, repeat_count * step - 1)
    expanded = dict(repeat_map)  # bestehende Peaks unverändert lassen
    _spread_repeat_to_neighbors(expanded, target, radius, repeat_count)

    # Diagnose: Schreibumfang & Range
    try:
        keys = sorted(expanded.keys())
        wrange = (keys[0], keys[-1]) if keys else (target, target)
        print(
            f"[JumpTo] target={target} repeat={repeat_count} "
            f"radius={radius} step={step} "
            f"write_frames={len(expanded)} range={wrange[0]}..{wrange[1]}"
        )
        if len(expanded) > 1:
            # Hinweis für Analyse: Merge-Strategie in properties.py
            print("[JumpTo] merge=MAX via record_repeat_bulk_map (see [RepeatMap] log)")
    except Exception:
        pass

    _kc_record_repeat_bulk_map(scn, expanded)

    # Diagnose: Serie/NZ-Anteil nach Merge
    try:
        series = scn.get("_kc_repeat_series") or []
        nz = sum(1 for v in series if v)
        fs, fe = int(scn.frame_start), int(scn.frame_end)
        n = max(0, fe - fs + 1)
        print(f"[JumpTo][Series] len={len(series)} expected={n} nonzero={nz}")
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
        print(f"[JumpTo][Repeat] saturated>= {REPEAT_SATURATION} at frame={int(target)} (repeat={int(repeat_count)})")

    # Rückgabe für aufrufenden Operator/Coordinator
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
    """Kompatibel zur alten Signatur:
    - liest 'scene["goto_frame"]'
    - ruft run_jump_to_frame()
    - gibt bool zurück (True bei OK)
    """
    res = run_jump_to_frame(context, frame=None, repeat_map=None)
    ok = (res.get("status") == "OK")
    return ok
