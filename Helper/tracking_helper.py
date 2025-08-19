# File: helper_track_selected.py
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Einzelnes, eigenständiges Helper-File zum Tracken bereits selektierter Marker
im Movie Clip Editor.

API:
    from helper_track_selected import track_selected_markers

    info = track_selected_markers(
        bpy.context,
        backwards=False,   # vorwärts
        sequence=True,     # über Sequenz
        reset_playhead=True
    )

Rückgabe: Dict mit {start_frame, tracked_until, scene_end, backwards, sequence}
– keine Abhängigkeiten zu Operatoren/Coordinator. PEP8-konform, gut kommentiert.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import bpy

__all__ = ("track_selected_markers",)


# ---------------------------------------------------------------------------
# Intern: Clip-Editor-Override finden (für zuverlässige Operator-Ausführung)
# ---------------------------------------------------------------------------

def _clip_editor_override(ctx: bpy.types.Context) -> Optional[dict[str, Any]]:
    """Sucht im aktiven Window eine CLIP_EDITOR-Area und liefert ein Override.

    Returns None, wenn kein Clip-Editor im aktuellen Window offen ist.
    """
    win = ctx.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if reg:
                return {"window": win, "screen": win.screen, "area": area, "region": reg}
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def track_selected_markers(context: bpy.types.Context,
                           *,
                           backwards: bool = False,
                           sequence: bool = True,
                           reset_playhead: bool = True) -> Dict[str, Any]:
    """Trackt *bereits selektierte* Marker via ``bpy.ops.clip.track_markers``.

    Parameters
    ----------
    context: bpy.types.Context
        Aktueller Blender-Kontext. Idealerweise aus einem Fenster mit Clip-Editor.
    backwards: bool, default False
        Rückwärts statt vorwärts tracken. (Anforderung: default False)
    sequence: bool, default True
        Über die gesamte Sequenz tracken. (Anforderung: default True)
    reset_playhead: bool, default True
        Nach dem Tracking den Playhead auf den Ursprungsframe zurücksetzen.

    Returns
    -------
    dict
        Informationen zum Lauf: start_frame, tracked_until, scene_end, backwards, sequence

    Raises
    ------
    RuntimeError
        Wenn kein Scene-Kontext oder kein CLIP_EDITOR-Override gefunden wird.
    """
    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")

    override = _clip_editor_override(context)
    if override is None:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    # Ausgangs- und Endframe merken
    start_frame = int(scene.frame_current)
    scene_end = int(scene.frame_end)

    # Tracking ausführen: selektierte Marker, vorwärts, sequence=True (oder wie übergeben)
    # Hinweis: Der Operator läuft synchron; bei Fehlern wirft Blender meist eine RuntimeError.
    bpy.ops.clip.track_markers(
        override,
        'EXEC_DEFAULT',
        backwards=bool(backwards),
        sequence=bool(sequence),
    )

    tracked_until = int(context.scene.frame_current)

    if reset_playhead:
        scene.frame_set(start_frame)

    return {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": scene_end,
        "backwards": bool(backwards),
        "sequence": bool(sequence),
    }
