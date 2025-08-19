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

Hinweis zum Playhead-Reset:
- Bei `EXEC_DEFAULT` ist das Tracking **synchron** → der Playhead wird zuverlässig
  nach Abschluss zurückgesetzt.
- Bei `INVOKE_DEFAULT` läuft der Tracking-Operator **modal/asynchron** weiter.
  Damit der Playhead trotzdem wieder auf den Startframe springt, registrieren wir
  einen kleinen Timer, der nach Ende der Bewegung zurücksetzt.
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
                               *, poll_every: float = 0.1, idle_ticks: int = 5) -> None:
    """Setzt den Playhead zurück, **nachdem** sich der Frame einige Ticks nicht
    mehr geändert hat (Heuristik für das Ende des modal laufenden Trackings).

    poll_every: Abtastintervall in Sekunden
    idle_ticks: Anzahl stabiler Abtastungen in Folge bis zum Reset
    """
    last = {"frame": None, "stable": 0}

    def _poll() -> Optional[float]:
        sc = context.scene
        if sc is None:
            return None
        cur = int(sc.frame_current)
        if last["frame"] == cur:
            last["stable"] += 1
        else:
            last["frame"] = cur
            last["stable"] = 0
        if last["stable"] >= idle_ticks:
            try:
                sc.frame_set(target_frame)
            except Exception:
                pass
            return None  # Timer beenden
        return poll_every

    # Timer registrieren (nach kurzer Verzögerung starten)
    try:
        bpy.app.timers.register(_poll, first_interval=poll_every)
    except Exception:
        # Fallback: sofort setzen, wenn Timer nicht verfügbar ist
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
        True  → nutze `INVOKE_DEFAULT` (modal), setze Playhead via Timer zurück.
        False → nutze `EXEC_DEFAULT` (synchron), setze Playhead direkt zurück.

    Returns
    -------
    Dict[str, Any]
        "start_frame", "tracked_until", "scene_end", "backwards" (False), "sequence" (True)
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
        # INVOKE: Operator läuft modal → Playhead-Reset per Timer
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                bpy.ops.clip.track_markers(
                    'INVOKE_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
            tracked_until = int(context.scene.frame_current)
        # remember_playhead setzt *sofort* zurück; der Operator bewegt aber
        # anschließend weiter. Deshalb zusätzlich per Timer final zurücksetzen.
        _schedule_playhead_restore(context, start_frame)
    else:
        # EXEC: synchron – wir können zuverlässig nach Abschluss zurücksetzen
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                bpy.ops.clip.track_markers(
                    'EXEC_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
            tracked_until = int(context.scene.frame_current)
        # remember_playhead setzte bereits zurück

    # Rückmeldung ablegen (optional Token)
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
