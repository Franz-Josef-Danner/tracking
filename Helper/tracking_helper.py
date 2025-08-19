# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py

Fix:
- Entfernt den zirkulären Import (dieses Modul importiert **nicht** mehr sich selbst).
- Bietet die Funktions‑API, die vom Coordinator genutzt wird.

Regeln umgesetzt:
1) Nur vorwärts tracken → `backwards=False`.
2) Operator‑Aufruf als `'INVOKE_DEFAULT'` (fallback EXEC), mit `sequence=True`.
3) Nach dem Tracken den Playhead auf den Ursprungs‑Frame zurücksetzen + Viewer redraw.

Hinweis zur INVOKE/EXEC‑Wahl:
`INVOKE_DEFAULT` startet in Blender üblicherweise eine modale Ausführung. Da eine verlässliche
Fertigstellungs‑Erkennung aus einem reinen Funktions‑Helper heraus nicht trivial ist, erzwingt diese
Funktion als Fallback einen synchronen `'EXEC_DEFAULT'`‑Aufruf, wenn der INVOKE‑Pfad nicht sofort
startet. Dadurch können wir den Playhead deterministisch zurücksetzen und das Token setzen.

Der Coordinator (`CLIP_OT_tracking_coordinator`) ruft diese Funktion mit `use_invoke=True` auf.
Das wird respektiert; sollte INVOKE nicht verfügbar sein, wird EXEC genutzt und geloggt.
"""
from __future__ import annotations

from typing import Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
)


# -----------------------------------------------------------------------------
# kleine Utilities
# -----------------------------------------------------------------------------

def _get_clip_area(context: bpy.types.Context) -> Optional[bpy.types.Area]:
    for area in getattr(context.window.screen, "areas", []):
        if area.type == 'CLIP_EDITOR':
            return area
    return None


def _redraw_clip_editors(context: bpy.types.Context) -> None:
    """Force‑Redraw aller Clip‑Editoren.

    Wird nach dem Playhead‑Reset aufgerufen, damit der sichtbare Viewer
    den Ursprungs‑Frame zeigt.
    """
    wm = context.window_manager
    for window in getattr(bpy.context, "window_manager", wm).windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


# -----------------------------------------------------------------------------
# Kern‑Helper: bis Szenenende tracken, Playhead zurück, Token setzen
# -----------------------------------------------------------------------------

def _do_track_forward(context: bpy.types.Context, *, use_invoke: bool) -> Tuple[bool, str]:
    """Startet das Vorwärts‑Tracking mit `sequence=True`.

    Returns (ok, message)
    """
    try:
        if use_invoke:
            # Regel 2: INVOKE_DEFAULT, sequence=True, backwards=False
            result = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            # INVOKE sollte i. d. R. 'RUNNING_MODAL' liefern – wir können nicht sicher
            # auf das Ende warten. Wenn INVOKE unmittelbar fehlschlägt, fallback auf EXEC.
            if result not in {{'RUNNING_MODAL', {'RUNNING_MODAL'}}}:
                exec_res = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)
                return (exec_res == {'FINISHED'}, f"EXEC_DEFAULT fallback → {exec_res}")
            return (True, "INVOKE_DEFAULT gestartet (modal)")
        else:
            exec_res = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)
            return (exec_res == {'FINISHED'}, f"EXEC_DEFAULT → {exec_res}")
    except Exception as ex:  # noqa: BLE001 – wir wollen jeden Ops‑Fehler abfangen
        return (False, f"Track‑Fehler: {ex}")


def track_to_scene_end_fn(
    context: bpy.types.Context,
    *,
    coord_token: Optional[str] = None,
    use_invoke: bool = True,
) -> None:
    """Trackt die aktiven Marker **vorwärts** bis zum Szenenende und setzt anschließend
    den Playhead auf den Ursprungs‑Frame zurück.

    Zusätzlich: optionales Token‑Feedback an den Coordinator über `wm["bw_tracking_done_token"]`.
    """
    scene = context.scene
    wm = context.window_manager

    # Ursprungs‑Frame merken (Regel 3)
    origin_frame: int = int(scene.frame_current)

    # Track auslösen (Regel 1 & 2)
    ok, info = _do_track_forward(context, use_invoke=use_invoke)

    # Wenn INVOKE gestartet wurde, haben wir i. d. R. RUNNING_MODAL. Wir kümmern uns **hier**
    # nur um den deterministischen Teil: Playhead‑Reset & Token setzen, sobald EXEC gelaufen ist
    # oder INVOKE sofort fertig wurde. Für den INVOKE‑Dauerfall übernimmt der Coordinator das
    # finale Redraw (er ruft _redraw_clip_editors() selbst) nachdem dieses Modul das Token setzt.

    # Bei echtem INVOKE (modal) können wir den Reset nicht unmittelbar machen ohne zu stören.
    # Daher: wenn INVOKE läuft, registrieren wir einen Timer, der den Reset verzögert ausführt.
    def _delayed_reset() -> Optional[float]:  # bpy.app.timers callback
        # Safe‑Reset des Playheads (Regel 3)
        try:
            scene.frame_set(origin_frame)
        except Exception:
            scene.frame_current = origin_frame
        # Viewer aktualisieren
        _redraw_clip_editors(context)
        # Feedback für den Coordinator
        if coord_token:
            wm["bw_tracking_done_token"] = coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": origin_frame,
                "tracked_until": int(scene.frame_current),
                "mode": "INVOKE" if use_invoke else "EXEC",
                "note": info,
            }
        return None  # einmalig

    if use_invoke and ok:
        # leichte Verzögerung, damit der INVOKE‑Operator Zeit zum Starten hat;
        # der Coordinator wartet modal auf das Token und triggert abschl. Redraw nochmal.
        import bpy.app.timers  # type: ignore

        bpy.app.timers.register(_delayed_reset, first_interval=0.25)
        return

    # EXEC‑Pfad oder INVOKE hat sofort beendet → direkt zurücksetzen
    try:
        scene.frame_set(origin_frame)
    except Exception:
        scene.frame_current = origin_frame
    _redraw_clip_editors(context)

    if coord_token:
        wm["bw_tracking_done_token"] = coord_token
        wm["bw_tracking_last_info"] = {
            "start_frame": origin_frame,
            "tracked_until": int(scene.frame_current),
            "mode": "EXEC" if not use_invoke else "INVOKE/instant",
            "note": info,
        }
