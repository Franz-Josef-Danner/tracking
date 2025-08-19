# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py – mit ausführlichen Konsolen‑Logs

Erfüllt deine Regeln 1–4 und fügt **detaillierte Debug‑Ausgaben** hinzu, um das
Playhead‑Reset‑Problem gezielt zu finden.

Log‑Präfix: "[BW-Track]"
"""
from __future__ import annotations

from typing import Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
)

LOG_PREFIX = "[BW-Track]"


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"{LOG_PREFIX} {msg}")


def _iter_clip_areas():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                yield window, area


def _get_active_clip_in_area(area: bpy.types.Area) -> Optional[bpy.types.MovieClip]:
    space = area.spaces.active if hasattr(area, "spaces") else None
    if space and getattr(space, "clip", None) is not None:
        return space.clip
    return None


def _get_any_clip() -> Optional[bpy.types.MovieClip]:
    for _w, area in _iter_clip_areas():
        clip = _get_active_clip_in_area(area)
        if clip is not None:
            return clip
    return None


def _redraw_clip_editors(_context: bpy.types.Context | None = None) -> None:
    for _w, area in _iter_clip_areas():
        for region in area.regions:
            if region.type == 'WINDOW':
                region.tag_redraw()


def _set_frame_and_notify(frame: int, *, verbose: bool = True) -> None:
    scene = bpy.context.scene
    if verbose:
        _log(f"Reset versuch: frame_set({frame}) – vorher: {scene.frame_current}")
    try:
        scene.frame_set(frame)
    except Exception as ex:
        _log(f"scene.frame_set Exception: {ex!r} – fallback scene.frame_current = {frame}")
        scene.frame_current = frame

    # UI‑Wechsel wie Benutzerinteraktion
    for window, area in _iter_clip_areas():
        override = {'window': window, 'screen': window.screen, 'area': area, 'region': None}
        try:
            bpy.ops.anim.change_frame(override, frame=frame)
            if verbose:
                _log(f"anim.change_frame in Area id={getattr(area,'as_pointer',lambda:None)()} ok")
        except Exception as ex:
            _log(f"anim.change_frame Exception in Area: {ex!r}")
    _redraw_clip_editors(None)
    if verbose:
        _log(f"Reset fertig – aktuell: {scene.frame_current}")


# -----------------------------------------------------------------------------
# Kern‑Helper: vorwärts tracken (INVOKE, sequence) → *nächster Tick* Frame‑Reset
# -----------------------------------------------------------------------------

def _start_forward_tracking_invoke(context: bpy.types.Context) -> Tuple[bool, str]:
    try:
        res = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        _log(f"track_markers INVOKE aufgerufen → result={res}")
        return True, f"track_markers INVOKE → {res}"
    except Exception as ex:  # noqa: BLE001
        _log(f"track_markers INVOKE Exception: {ex!r}")
        return False, f"Track‑Fehler: {ex}"


def track_to_scene_end_fn(
    context: bpy.types.Context,
    *,
    coord_token: Optional[str] = None,
    debug: bool = True,
) -> None:
    """Nur‑Vorwärts‑Tracking (INVOKE, sequence) und **danach** Playhead‑Reset.

    - Kein eigener Operator (Regel 1)
    - Nur vorwärts (Regel 2)
    - INVOKE_DEFAULT, backwards=False, sequence=True (Regel 3)
    - Playhead‑Reset auf Ursprungs‑Frame (Regel 4)

    Mit **Debug‑Logs** zur Fehlersuche.
    """
    wm = context.window_manager
    scene = context.scene

    # Clip / Areas loggen
    areas = list(_iter_clip_areas())
    if debug:
        _log(f"Gefundene CLIP_EDITOR Areas: {len(areas)}")
    clip = _get_any_clip()
    if clip is None:
        _log("Kein aktiver MovieClip gefunden – Abbruch")
        raise RuntimeError("Kein aktiver MovieClip im CLIP_EDITOR gefunden.")
    if debug:
        _log(f"Clip Name: {getattr(clip,'name','<unnamed>')}")

    origin_frame: int = int(scene.frame_current)
    if debug:
        _log(f"Origin Frame: {origin_frame}")

    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        raise RuntimeError(info)

    # Delayed Reset Tick 1 -----------------------------------------------------
    def _tick_once() -> Optional[float]:
        if debug:
            _log("Timer Tick #1 – versuche Reset auf Origin")
        before = int(bpy.context.scene.frame_current)
        _set_frame_and_notify(origin_frame, verbose=debug)
        after = int(bpy.context.scene.frame_current)
        if debug:
            _log(f"Timer Tick #1 – Frame vorher={before}, nachher={after}")
        # Falls der Frame *nicht* auf origin steht, zweiter Versuch später
        if after != origin_frame:
            if debug:
                _log("Timer Tick #1 – Reset nicht wirksam, plane Tick #2 in 0.3s")
            bpy.app.timers.register(_tick_twice, first_interval=0.3)
        else:
            if coord_token:
                wm["bw_tracking_done_token"] = coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": origin_frame,
                "tracked_until": int(bpy.context.scene.frame_current),
                "mode": "INVOKE",
                "note": info,
                "tick": 1,
            }
            if debug:
                _log("Timer Tick #1 – Reset erfolgreich, Token gesetzt")
        return None

    # Delayed Reset Tick 2 (Fallback) -----------------------------------------
    def _tick_twice() -> Optional[float]:
        if debug:
            _log("Timer Tick #2 – erneuter Reset‑Versuch")
        before = int(bpy.context.scene.frame_current)
        _set_frame_and_notify(origin_frame, verbose=debug)
        after = int(bpy.context.scene.frame_current)
        if coord_token:
            wm["bw_tracking_done_token"] = coord_token
        wm["bw_tracking_last_info"] = {
            "start_frame": origin_frame,
            "tracked_until": int(bpy.context.scene.frame_current),
            "mode": "INVOKE",
            "note": info,
            "tick": 2,
        }
        if debug:
            _log(f"Timer Tick #2 – Frame vorher={before}, nachher={after}; Token gesetzt")
        return None

    # Timer starten (0.12s gibt INVOKE minimal Zeit zu starten, aber bleibt snappy)
    if debug:
        _log("Register Timer Tick #1 in 0.12s")
    bpy.app.timers.register(_tick_once, first_interval=0.12)
