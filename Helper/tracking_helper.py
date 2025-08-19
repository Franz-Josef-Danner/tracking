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
