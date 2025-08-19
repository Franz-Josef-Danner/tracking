# =========================
# File: Helper/tracking_helper.py
# =========================
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Function-only Helper für Tracking im Movie Clip Editor.

Bereitgestellt wird **nur**:

    track_to_scene_end_fn(context, *, coord_token: str = "") -> dict

Die Funktion:
- findet einen CLIP_EDITOR im aktuellen Window
- ruft **INVOKE_DEFAULT** auf `bpy.ops.clip.track_markers` innerhalb eines
  `context.temp_override(window, area, region, space_data)`
- setzt den Playhead nach dem Tracken wieder auf den Startframe zurück
- legt Feedback im WindowManager ab (Token + Info-Dict)
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import bpy

__all__ = ("track_to_scene_end_fn",)


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
# Public API: Funktionsbasierter Helper
# ---------------------------------------------------------------------------

def track_to_scene_end_fn(context: bpy.types.Context, *, coord_token: str = "") -> Dict[str, Any]:
    """Trackt **selektierte Marker** vorwärts über die Sequenz per INVOKE_DEFAULT.

    Parameters
    ----------
    context : bpy.types.Context
        Aktueller Blender-Kontext (mit offenem CLIP_EDITOR im aktiven Window).
    coord_token : str, optional
        Wenn gesetzt, schreibt der Helper das Token in
        ``context.window_manager["bw_tracking_done_token"]``.

    Returns
    -------
    Dict[str, Any]
        "start_frame", "tracked_until", "scene_end", "backwards" (False), "sequence" (True)

    Raises
    ------
    RuntimeError
        Wenn kein CLIP_EDITOR-Override gefunden wird oder der Operatorlauf fehlschlägt.
    """
    handles = _clip_editor_handles(context)
    if not handles:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")

    wm = context.window_manager
    start_frame = int(scene.frame_current)
    end_frame = int(scene.frame_end)

    # Tracking ausführen – robust im UI-Kontext des Clip-Editors
    try:
        with context.temp_override(**handles):
            bpy.ops.clip.track_markers(
                'INVOKE_DEFAULT',
                backwards=False,  # nur vorwärts
                sequence=True,    # über gesamte Sequenz
            )
    except Exception as ex:
        raise RuntimeError(f"track_markers fehlgeschlagen: {ex}") from ex

    tracked_until = int(context.scene.frame_current)

    # Playhead zurücksetzen
    scene.frame_set(start_frame)

    # Rückmeldung ablegen (optional Token)
    if coord_token:
        wm["bw_tracking_done_token"] = coord_token
    info = {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": end_frame,
        "backwards": False,
        "sequence": True,
    }
    wm["bw_tracking_last_info"] = info
    return info
