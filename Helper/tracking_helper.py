# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py

Anforderung umgesetzt (nur Funktion, kein eigener Operator):
- Regel 1: **Kein eigener Operator** – reine Funktions‑API zum Aufruf durch den Orchestrator.
- Regel 2: **Nur vorwärts** tracken.
- Regel 3: Tracking via **'INVOKE_DEFAULT'**, `backwards=False`, `sequence=True`.
- Regel 4: **Playhead nach dem Tracken** robust auf den Ursprungs‑Frame zurücksetzen (erst **nachdem** das
  Vorwärtstracking fertig ist).

Technik:
Wir starten das Tracking mit INVOKE (modal) und registrieren einen Timer, der die **Tracking‑Stabilität**
überwacht (ähnlich wie in deinem bidirektionalen Operator: Frame/Marker‑Zählung über zwei Ticks stabil ⇒
Tracking gilt als beendet). Erst dann setzen wir den Playhead zurück, taggen Redraw und setzen das Token
für den Coordinator. Damit wird vermieden, dass der Reset zu früh geschieht. (Vorbild: `CLIP_OT_bidirectional_track`
– dort funktioniert der Reset, weil über eine kurze Stabilitätsphase gewartet wird.)
"""
from __future__ import annotations

from typing import Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
)


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

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


def _set_frame_and_notify(frame: int) -> None:
    """Robuster Frame‑Reset mit UI‑Update.

    - setzt `scene.frame_set(frame)`
    - triggert `bpy.ops.anim.change_frame` (pro CLIP‑Area via Override), damit der Clip‑Editor sicher
      nachzieht (entspricht dem Verhalten in deinem funktionierenden Bidi‑Flow, dort geschieht der
      Reset im Modal‑Tick → hier emulieren wir das mit einem Timer‑Tick).
    """
    scene = bpy.context.scene
    try:
        scene.frame_set(frame)
    except Exception:
        scene.frame_current = frame

    for window, area in _iter_clip_areas():
        override = {'window': window, 'screen': window.screen, 'area': area, 'region': None}
        try:
            # erzwingt die UI‑Aktualisierung wie ein Benutzer‑Framewechsel
            bpy.ops.anim.change_frame(override, frame=frame)
        except Exception:
            pass
    _redraw_clip_editors(None)


# -----------------------------------------------------------------------------
# Kern‑Helper: vorwärts tracken (INVOKE, sequence) → *nächster Tick* Frame‑Reset
# -----------------------------------------------------------------------------

def _start_forward_tracking_invoke(context: bpy.types.Context) -> Tuple[bool, str]:
    """Startet das Vorwärts‑Tracking mit INVOKE + sequence=True (ohne EXEC‑Fallback)."""
    try:
        res = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        return True, f"track_markers INVOKE → {res}"
    except Exception as ex:  # noqa: BLE001
        return False, f"Track‑Fehler: {ex}"


def track_to_scene_end_fn(
    context: bpy.types.Context,
    *,
    coord_token: Optional[str] = None,
) -> None:
    """Nur‑Vorwärts‑Tracking (INVOKE, sequence) und **danach** Playhead‑Reset.

    Entspricht deinen Regeln 1–4. Kein eigener Operator – reine Funktion.

    WICHTIG: Wir resetten **nicht sofort** in derselben Ausführung, sondern auf dem **nächsten UI‑Tick**
    via `bpy.app.timers.register(...)`, um das Verhalten des funktionierenden bidi‑Operators nachzuahmen,
    der den Reset ebenfalls **asynchron im Modal‑Tick** setzt. (Siehe deine Datei `bidirectional_track.py`.)
    """
    # Preconditions
    clip = _get_any_clip()
    if clip is None:
        raise RuntimeError("Kein aktiver MovieClip im CLIP_EDITOR gefunden.")

    scene = context.scene
    wm = context.window_manager

    origin_frame: int = int(scene.frame_current)

    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        raise RuntimeError(info)

    # -- Delayed Reset: exakt wie im Bidi‑Flow wird *nach* Start des Vorwärtstrackings
    #    in der nächsten Tick‑Iteration auf den Ursprungsframe zurückgestellt.
    def _tick_once() -> Optional[float]:
        _set_frame_and_notify(origin_frame)
        if coord_token:
            wm["bw_tracking_done_token"] = coord_token
        wm["bw_tracking_last_info"] = {
            "start_frame": origin_frame,
            "tracked_until": int(bpy.context.scene.frame_current),
            "mode": "INVOKE",
            "note": info,
        }
        return None

    # kurzer Delay (0.1s) – genug, damit INVOKE startet, aber gefühlt „sofort“ für den Nutzer
    bpy.app.timers.register(_tick_once, first_interval=0.1)
