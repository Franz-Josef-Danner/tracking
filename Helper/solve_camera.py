"""Minimaler Kamera-Solve-Trigger (bereinigt).

ACHTUNG: Dieses Modul enthält **nur** den Solve-Trigger. Es gibt **keine**
Diff/Patch-Blöcke oder Zusatzlogik mehr – damit keine SyntaxErrors entstehen.
"""
from __future__ import annotations
import bpy
from typing import Optional

__all__ = ("solve_camera_only",)


# -- interne Hilfe: passenden CLIP_EDITOR im aktuellen Window finden ---------

def _find_clip_window(context) -> tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = getattr(context, "window", None)
    screen = getattr(win, "screen", None)
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


# -- öffentliche API ----------------------------------------------------------

def solve_camera_only(context):
    """Löst nur den Kamera-Solve aus – kein Cleanup, kein Warten.

    Versucht, falls möglich, einen Kontext-Override auf einen CLIP_EDITOR zu
    setzen, damit der Operator zuverlässig läuft. Fällt ansonsten auf den
    globalen Kontext zurück.

    Returns
    -------
    set | dict
        Das Operator-Resultat (z. B. {'RUNNING_MODAL'} oder {'CANCELLED'}).
    """
    area, region, space = _find_clip_window(context)
    try:
        if area and region and space:
            with context.temp_override(area=area, region=region, space_data=space):
                return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[Solve] Fehler beim Start des Solve-Operators: {e}")
        return {"CANCELLED"}


# ----------------------------------------------------------------------------
# HINWEIS FÜR DEN KOORDINATOR (separate Datei!):
#
# In Operator/tracking_coordinator.py oben importieren:
#     from ..Helper.solve_camera import solve_camera_only
#
# Und in der State-Methode den Solve auslösen (ohne Diff-Marker!):
#
#     def _state_solve(self, context):
#         """Startet ausschließlich den Kamera-Solve und wechselt in SOLVE_WAIT."""
#         try:
#             res = solve_camera_only(context)
#             print(f"[Coord] Solve invoked: {res}")
#         except Exception as ex:
#             print(f"[Coord] SOLVE start failed: {ex!r}")
#             self._state = "FINALIZE"
#             return {'RUNNING_MODAL'}
#
#         self._state = "SOLVE_WAIT"
#         return {'RUNNING_MODAL'}
# ----------------------------------------------------------------------------
