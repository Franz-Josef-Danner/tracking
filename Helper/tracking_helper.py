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

Hinweis Playhead-Reset bei INVOKE:
`INVOKE_DEFAULT` startet den Blender-Operator **modal**. Deshalb kann der
Operator nach Funktionsrückkehr weiterhin den Playhead bewegen. Um den
Ausgangsframe dennoch **zuverlässig** wiederherzustellen, nutzen wir eine
zweistufige Timer-Heuristik ("settle" + "enforce").
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Optional, Iterator
import bpy

__all__ = ("track_to_scene_end_fn", "remember_playhead")


# ---------------------------------------------------------------------------
# Intern: Clip-Editor-Handles suchen
# ---------------------------------------------------------------------------

def _clip_editor_handles(ctx: bpy.types.Context) -> Optional[Dict[str, Any]]:
    win = ctx.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {"window": win, "area": area, "region": region, "space_data": space}
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

    def _poll():
        sc = context.scene
        if sc is None:
            return None
        cur = int(sc.frame_current)

        if state["phase"] == "settle":
            if state["last"] == cur:
                state["stable"] += 1
            else:
                state["last"] = cur
                state["stable"] = 0
            if state["stable"] >= settle_ticks:
                try:
                    sc.frame_set(target_frame)
                except Exception:
                    pass
                state["phase"] = "enforce"
                state["enforce"] = 0
            return interval

        # enforce-Phase: ein paar Ticks lang "festnageln"
        if cur != target_frame:
            try:
                sc.frame_set(target_frame)
            except Exception:
                pass
            state["enforce"] = 0  # erneut stabilisieren
        else:
            state["enforce"] += 1
        if state["enforce"] >= enforce_ticks:
            return None  # fertig – Timer entfernen
        return interval

    try:
        bpy.app.timers.register(_poll, first_interval=interval)
    except Exception:
        # Fallback: direkter Setzversuch
        try:
            context.scene.frame_set(target_frame)
        except Exception:
            pass


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
    try:
        yield start_frame
    finally:
        try:
            scene.frame_set(start_frame)
        except Exception:
            pass


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
    handles = _clip_editor_handles(context)
    if not handles:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")

    wm = context.window_manager
    end_frame = int(scene.frame_end)

    if use_invoke:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                bpy.ops.clip.track_markers(
                    'INVOKE_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
            tracked_until = int(context.scene.frame_current)
        # Zusätzliche Sicherung nach modalem Finish
        _schedule_playhead_restore(context, start_frame)
    else:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                bpy.ops.clip.track_markers(
                    'EXEC_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
            tracked_until = int(context.scene.frame_current)
        # remember_playhead hat bereits zurückgesetzt

    if coord_token:
        wm["bw_tracking_done_token"] = coord_token

    info = {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": end_frame,
        "backwards": False,
        "sequence": True,
        "mode": "INVOKE" if use_invoke else "EXEC",
    }
    wm["bw_tracking_last_info"] = info
    return info
