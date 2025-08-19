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

def _get_clip_from_context(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Versucht, einen aktiven MovieClip aus dem CLIP_EDITOR zu holen."""
    area = getattr(context, "area", None)
    if area and area.type == 'CLIP_EDITOR':
        space = getattr(context, "space_data", None)
        if space and getattr(space, "clip", None) is not None:
            return space.clip
    # Fallback: in allen Fenstern/Areas suchen
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                space = area.spaces.active
                if getattr(space, "clip", None) is not None:
                    return space.clip
    return None


def _redraw_clip_editors(context: bpy.types.Context) -> None:
    """Force‑Redraw aller Clip‑Editoren."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


# -----------------------------------------------------------------------------
# Kern‑Helper: vorwärts tracken (INVOKE, sequence) → nach Ende Reset auf Ursprungs‑Frame
# -----------------------------------------------------------------------------

def _start_forward_tracking_invoke(context: bpy.types.Context) -> Tuple[bool, str]:
    """Startet das Vorwärts‑Tracking mit INVOKE + sequence=True.

    Liefert (ok, info) zurück. **Kein** EXEC‑Fallback – Vorgabe verlangt INVOKE.
    """
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

    Diese Funktion ist **ohne eigenen Operator** nutzbar (Regel 1) und gibt selbst nichts zurück.
    Der Abschluss wird über `wm["bw_tracking_done_token"]` signalisiert, kompatibel zum
    Orchestrator. (Vorbild/Referenzlogik: bidirektionaler Operator mit Stabilitäts‑Check.)
    """
    wm = context.window_manager
    scene = context.scene

    # 1) Preconditions: aktiver Clip vorhanden?
    clip = _get_clip_from_context(context)
    if clip is None:
        raise RuntimeError("Kein aktiver MovieClip im CLIP_EDITOR gefunden.")

    # 2) Ursprungs‑Frame merken (für Reset nach Abschluss)
    origin_frame: int = int(scene.frame_current)

    # 3) Vorwärts‑Tracking via INVOKE_DEFAULT starten (Regel 2 & 3)
    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        raise RuntimeError(info)

    # 4) Timer registrieren, der auf **Ende** des Trackings wartet (Stabilität über 2 Ticks)
    state = {
        "prev_frame": -10**9,
        "prev_count": -10**9,
        "stable": 0,
        "origin": origin_frame,
        "token": coord_token,
    }

    def _is_tracking_stable() -> bool:
        # Zähle Marker (gesamt) und lese aktuellen Frame – heuristisch ausreichend, wie im Bidi‑Op.
        current_frame = int(scene.frame_current)
        try:
            current_count = sum(len(t.markers) for t in clip.tracking.tracks)
        except Exception:
            current_count = -1
        if state["prev_frame"] == current_frame and state["prev_count"] == current_count:
            state["stable"] += 1
        else:
            state["stable"] = 0
        state["prev_frame"] = current_frame
        state["prev_count"] = current_count
        # Zwei aufeinanderfolgende stabile Ticks ⇒ fertig (analog zum Beispielcode)
        return state["stable"] >= 2

    def _timer_cb() -> Optional[float]:
        try:
            if not _is_tracking_stable():
                return 0.25  # weiter pollen
            # Fertig erkannt → Reset auf Ursprungs‑Frame (Regel 4)
            try:
                scene.frame_set(state["origin"])
            except Exception:
                scene.frame_current = state["origin"]
            _redraw_clip_editors(context)
            # Token/Info für Orchestrator setzen
            if state["token"]:
                wm["bw_tracking_done_token"] = state["token"]
            wm["bw_tracking_last_info"] = {
                "start_frame": state["origin"],
                "tracked_until": int(scene.frame_current),
                "mode": "INVOKE",
                "note": info,
            }
        finally:
            # Timer beenden (None)
            return None

    # Timer starten (poll alle 0.25s)
    bpy.app.timers.register(_timer_cb, first_interval=0.25)
