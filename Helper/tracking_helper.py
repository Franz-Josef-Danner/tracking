# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py – mit ausführlichen Konsolen‑Logs (FIXED)

✔ Regel 1: **Kein eigener Operator**, nur Funktions‑API
✔ Regel 2: **Nur vorwärts** tracken
✔ Regel 3: `INVOKE_DEFAULT`, `backwards=False`, `sequence=True`
✔ Regel 4: **Playhead** nach dem Tracken **zurück** auf Ursprungs‑Frame

Zusätzlich:
- Behebt `SyntaxError` durch Entfernen eines versehentlich stehen gebliebenen Funktionsfragments.
- Robustere UI‑Aktualisierung ohne `bpy.ops.anim.change_frame` (verursachte Kontext‑Fehler), stattdessen
  `scene.frame_set(...)` + `region.tag_redraw()` auf allen CLIP‑Editor‑Fenstern.
- Watch‑Loop hält den Playhead auf dem Ursprungs‑Frame, bis er 2 Ticks stabil ist.

Log‑Präfix: "[BW-Track]"
"""
from __future__ import annotations

from typing import Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
    "_test_reset_only",  # einfache Selbsttests
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
    """Force‑Redraw aller Clip‑Editoren."""
    for _w, area in _iter_clip_areas():
        for region in area.regions:
            if region.type == 'WINDOW':
                region.tag_redraw()


def _set_frame_and_notify(frame: int, *, verbose: bool = True) -> None:
    """Robuster Frame‑Reset + UI‑Redraw ohne `anim.change_frame`.

    `anim.change_frame` führte im Override zu ValueErrors (abhängig vom Kontext). Für den Clip‑Editor
    reicht hier i. d. R. `scene.frame_set` + `tag_redraw` aus.
    """
    scene = bpy.context.scene
    if verbose:
        _log(f"Reset versuch: frame_set({frame}) – vorher: {scene.frame_current}")
    try:
        scene.frame_set(frame)
    except Exception as ex:
        _log(f"scene.frame_set Exception: {ex!r} – fallback scene.frame_current = {frame}")
        scene.frame_current = frame
    _redraw_clip_editors(None)
    if verbose:
        _log(f"Reset fertig – aktuell: {scene.frame_current}")


def _furthest_tracked_frame(clip: bpy.types.MovieClip) -> int:
    """Ermittle den maximalen Marker‑Frame im Clip (Diagnose)."""
    mx = 0
    try:
        for tr in getattr(clip.tracking, "tracks", []):
            for m in getattr(tr, "markers", []):
                f = int(getattr(m, "frame", 0))
                if f > mx:
                    mx = f
    except Exception:
        pass
    return mx


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
    watch_interval: float = 0.2,
    watch_stable_ticks: int = 2,
    first_delay: float = 0.25,
) -> None:
    """Nur‑Vorwärts‑Tracking (INVOKE, sequence) und **danach** Playhead‑Reset.

    - Kein eigener Operator (Regel 1)
    - Nur vorwärts (Regel 2)
    - INVOKE_DEFAULT, backwards=False, sequence=True (Regel 3)
    - Playhead‑Reset auf Ursprungs‑Frame (Regel 4)

    Mit **Debug‑Logs** und einer Watch‑Loop, die den Playhead für einige Ticks stabil hält.
    """
    wm = context.window_manager
    scene = context.scene

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
        _log(f"Vor Start: furthest_tracked={_furthest_tracked_frame(clip)}")

    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        raise RuntimeError(info)

    # Diagnose + erster Reset nach kleinem Delay --------------------------------
    def _tick_once() -> Optional[float]:
        if debug:
            _log("Timer Tick #1 – versuche Reset auf Origin")
            _log(
                f"Tick #1 Diagnose: scene.frame_current={int(bpy.context.scene.frame_current)}, "
                f"furthest_tracked={_furthest_tracked_frame(clip)}"
            )
        before = int(bpy.context.scene.frame_current)
        _set_frame_and_notify(origin_frame, verbose=debug)
        after = int(bpy.context.scene.frame_current)
        if debug:
            _log(f"Timer Tick #1 – Frame vorher={before}, nachher={after}")
        # Starte Watch‑Loop, die den Playhead hält, bis Stabilität erkannt ist
        bpy.app.timers.register(_watch_reset, first_interval=watch_interval)
        return None

    # Watch‑Loop: Playhead bis Stabilität halten --------------------------------
    state = {"stable": 0}

    def _watch_reset() -> Optional[float]:
        cur = int(bpy.context.scene.frame_current)
        if cur == origin_frame:
            state["stable"] += 1
        else:
            state["stable"] = 0
            if debug:
                _log(f"Watch: Frame != origin ({cur} != {origin_frame}) → setze erneut")
            _set_frame_and_notify(origin_frame, verbose=False)
        if state["stable"] >= watch_stable_ticks:
            if coord_token:
                wm["bw_tracking_done_token"] = coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": origin_frame,
                "tracked_until": int(bpy.context.scene.frame_current),
                "mode": "INVOKE",
                "note": info,
                "watch_stable": state["stable"],
            }
            if debug:
                _log("Watch: stabil erreicht → Token gesetzt, beende Watch")
            return None
        return watch_interval

    if debug:
        _log(f"Register Timer Tick #1 in {first_delay:.2f}s")
    bpy.app.timers.register(_tick_once, first_interval=first_delay)


# -----------------------------------------------------------------------------
# Einfache Selbsttests (innerhalb von Blender im Text‑Editor/Console aufrufbar)
# -----------------------------------------------------------------------------

def _test_reset_only(context: bpy.types.Context, *, delta: int = 5) -> None:
    """Kleiner Sanity‑Test für den Reset:

    1) merkt sich aktuellen Frame `f0`
    2) setzt Szene auf `f0 + delta`
    3) ruft `_set_frame_and_notify(f0)`
    4) prüft, dass die Szene wieder auf `f0` steht

    Aufruf in der Blender‑Konsole:
        >>> import importlib, Helper.tracking_helper as th
        >>> importlib.reload(th); th._test_reset_only(bpy.context)
    """
    scene = context.scene
    f0 = int(scene.frame_current)
    scene.frame_set(f0 + int(delta))
    _set_frame_and_notify(f0, verbose=True)
    assert int(scene.frame_current) == f0, (
        f"Reset fehlgeschlagen: erwartet {f0}, ist {int(scene.frame_current)}"
    )
    _log("_test_reset_only: OK")
