# =========================
# File: Helper/tracking_helper.py
# =========================
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Function-only Helper für Tracking im Movie Clip Editor.

Bereitgestellt wird:

    track_to_scene_end_fn(context, *, coord_token: str = "", use_invoke: bool = True) -> dict
    remember_playhead(context) -> Contextmanager, der den Startframe merkt und
                                 den Playhead beim Verlassen zurücksetzt.

Mit **Konsolen-Logs** zur Diagnose (Windows: *Window → Toggle System Console*):
- Start/Ende der Funktion
- gefundene Handles/Start-Frame/End-Frame
- Operator-Aufruf und Rückgabeset
- Sofort gemessener `tracked_until`
- Playhead-Restore (Context-Manager + Timer-Phasen)
- Token/Info-Write in den WindowManager
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Optional, Iterator
import bpy

__all__ = ("track_to_scene_end_fn", "remember_playhead")

# --- Debugging-Schalter ------------------------------------------------------
DEBUG = True

def _log(msg: str) -> None:
    if DEBUG:
        print(f"[Kaiserlich/Helper] {msg}")


# ---------------------------------------------------------------------------
# Intern: Clip-Editor-Handles suchen
# ---------------------------------------------------------------------------

def _clip_editor_handles(ctx: bpy.types.Context) -> Optional[Dict[str, Any]]:
    win = ctx.window
    if not win or not win.screen:
        _log("kein window/screen im Context")
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                _log("CLIP_EDITOR gefunden (handles ok)")
                return {"window": win, "area": area, "region": region, "space_data": space}
    _log("kein CLIP_EDITOR im aktuellen Window gefunden")
    return None


# ---------------------------------------------------------------------------
# Intern: Playhead nach INVOKE zuverlässig zurücksetzen (Timer)
# ---------------------------------------------------------------------------

def _schedule_playhead_restore(context: bpy.types.Context, target_frame: int,
                               *, interval: float = 0.10,
                               settle_ticks: int = 8,
                               enforce_ticks: int = 10) -> None:
    """Stellt den Playhead **nach Abschluss** der modalen Bewegung wieder her.

    Ablauf:
    - *settle*-Phase: Warten, bis sich `frame_current` `settle_ticks` mal
      hintereinander **nicht** geändert hat (Tracking ist zur Ruhe gekommen).
    - *enforce*-Phase: Danach `enforce_ticks` lang sicherstellen, dass der
      Playhead auf `target_frame` bleibt (falls spät noch etwas verschiebt).
    """
    state = {"last": None, "stable": 0, "phase": "settle", "enforce": 0}
    _log(f"Timer registrieren: target_frame={target_frame}, interval={interval}s, settle={settle_ticks}, enforce={enforce_ticks}")

    def _poll():
        sc = context.scene
        if sc is None:
            _log("Timer: kein Scene-Kontext mehr – breche ab")
            return None
        cur = int(sc.frame_current)

        if state["phase"] == "settle":
            if state["last"] == cur:
                state["stable"] += 1
            else:
                state["last"] = cur
                state["stable"] = 0
            _log(f"Timer/settle: cur={cur}, stable={state['stable']}")
            if state["stable"] >= settle_ticks:
                try:
                    sc.frame_set(target_frame)
                    _log(f"Timer/settle: setze Frame -> {target_frame}")
                except Exception as ex:
                    _log(f"Timer/settle: frame_set Fehler: {ex}")
                state["phase"] = "enforce"
                state["enforce"] = 0
            return interval

        # enforce-Phase: ein paar Ticks lang "festnageln"
        if cur != target_frame:
            try:
                sc.frame_set(target_frame)
                _log(f"Timer/enforce: korrigiere Frame {cur} -> {target_frame}")
            except Exception as ex:
                _log(f"Timer/enforce: frame_set Fehler: {ex}")
            state["enforce"] = 0
        else:
            state["enforce"] += 1
            _log(f"Timer/enforce: ok (cur={cur}), ok_ticks={state['enforce']}")
        if state["enforce"] >= enforce_ticks:
            _log("Timer: fertig – entferne Timer")
            return None  # Timer entfernen
        return interval

    try:
        bpy.app.timers.register(_poll, first_interval=interval)
    except Exception as ex:
        _log(f"Timer-Registrierung fehlgeschlagen: {ex} – setze sofort target")
        try:
            context.scene.frame_set(target_frame)
        except Exception as ex2:
            _log(f"Fallback frame_set Fehler: {ex2}")


# ---------------------------------------------------------------------------
# Public API: Playhead merken/zurücksetzen
# ---------------------------------------------------------------------------

@contextmanager
def remember_playhead(context: bpy.types.Context) -> Iterator[int]:
    """Merkt den aktuellen Scene-Frame und setzt ihn beim Verlassen zurück."""
    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")
    start_frame = int(scene.frame_current)
    _log(f"remember_playhead: merke start_frame={start_frame}")
    try:
        yield start_frame
    finally:
        try:
            scene.frame_set(start_frame)
            _log(f"remember_playhead: setze zurück -> {start_frame}")
        except Exception as ex:
            _log(f"remember_playhead: frame_set Fehler: {ex}")


# ---------------------------------------------------------------------------
# Public API: Funktionsbasierter Helper
# ---------------------------------------------------------------------------

def track_to_scene_end_fn(context: bpy.types.Context, *, coord_token: str = "", use_invoke: bool = True) -> Dict[str, Any]:
    """Trackt **selektierte Marker** vorwärts über die Sequenz.

    Parameters
    ----------
    context : bpy.types.Context
        Aktueller Blender-Kontext (mit offenem CLIP_EDITOR im aktiven Window).
    coord_token : str, optional
        Wenn gesetzt, schreibt der Helper das Token in
        ``context.window_manager["bw_tracking_done_token"]``.
    use_invoke : bool, default True
        True  → nutze `INVOKE_DEFAULT` (modal) + Timer-Reset
        False → nutze `EXEC_DEFAULT` (synchron) + direkten Reset

    Returns
    -------
    Dict[str, Any]
        "start_frame", "tracked_until", "scene_end", "backwards" (False), "sequence" (True), "mode"
    """
    _log(f"track_to_scene_end_fn: start (use_invoke={use_invoke})")
    handles = _clip_editor_handles(context)
    if not handles:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")

    wm = context.window_manager
    end_frame = int(scene.frame_end)
    _log(f"Frames: current={int(scene.frame_current)}, scene_end={end_frame}")

    if use_invoke:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                _log("rufe bpy.ops.clip.track_markers('INVOKE_DEFAULT', fwd, seq=True) auf …")
                ret = bpy.ops.clip.track_markers(
                    'INVOKE_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
                _log(f"Operator-Return (INVOKE): {ret}")
            tracked_until = int(context.scene.frame_current)
            _log(f"tracked_until (sofort nach Call): {tracked_until}")
        _schedule_playhead_restore(context, start_frame)
    else:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                _log("rufe bpy.ops.clip.track_markers('EXEC_DEFAULT', fwd, seq=True) auf …")
                ret = bpy.ops.clip.track_markers(
                    'EXEC_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
                _log(f"Operator-Return (EXEC): {ret}")
            tracked_until = int(context.scene.frame_current)
            _log(f"tracked_until (nach EXEC): {tracked_until}")

    if coord_token:
        wm["bw_tracking_done_token"] = coord_token
        _log(f"WM-Token gesetzt -> {coord_token}")

    info = {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": end_frame,
        "backwards": False,
        "sequence": True,
        "mode": "INVOKE" if use_invoke else "EXEC",
    }
    wm["bw_tracking_last_info"] = info
    _log(f"Info geschrieben: {info}")
    _log("track_to_scene_end_fn: fertig")
    return info
