"""Helper: Vorwärts-Tracking selektierter Marker.

Stellt eine bequeme Funktion bereit, um selektierte Marker per
`bpy.ops.clip.track_markers` nach vorne zu tracken.

Blender Operator Referenz (vereinfacht):
    bpy.ops.clip.track_markers(backwards=False, sequence=True)

Parameter laut API:
    backwards (bool) – Rückwärts tracken
    sequence  (bool) – Über die Bildsequenz hinweg tracken (statt nur ein Bild)

Diese Helper-Funktion kapselt:
  - Kontext-Übersteuerung (falls nötig) für CLIP_EDITOR
  - Existenzprüfung von Clip und Tracking Daten
  - Rückgabe eines einfachen Erfolgs-Flags

Hinweis:
  Mit sequence=True versucht Blender den Track bis zum Ende oder bis zum ersten
  Fehlschlag fortzuführen. Eine direkte Limitierung auf N Frames ist damit
  nicht möglich; dafür weiterhin frameweises manuelles Aufrufen ohne sequence
  benutzen.
"""

from __future__ import annotations
import bpy
from typing import Tuple, Optional

def _find_clip_editor_area(clip) -> Tuple[Optional[object], Optional[object], Optional[object], Optional[object]]:
    """Sucht ein Fenster/Area/Region/Space für den CLIP_EDITOR zur Context Override.

    Rückgabe: (window, area, region_window, space) oder (None, ...)
    """
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        if getattr(space, 'clip', None) == clip or space.clip is None:
                            region_window = None
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    region_window = region
                                    break
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None


def track_forward_selected_markers(context, *, sequence: bool = True, backwards: bool = False) -> bool:
    """Trackt die aktuell selektierten Marker vorwärts.

    Args:
        context: Blender Kontext
        sequence: True -> kompletter Sequenzlauf; False -> nur ein Frame Schritt
        backwards: True -> rückwärts statt vorwärts

    Returns:
        bool: True bei Erfolg (Operator nicht "CANCELLED"), sonst False.
    """
    clip = context.space_data.clip if getattr(context, 'space_data', None) else None
    if clip is None:
        print("[Kaiserlich Tracker] track_forward: Kein Clip aktiv.")
        return False
    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        print("[Kaiserlich Tracker] track_forward: Clip besitzt kein tracking.")
        return False

    selected = [t for t in tracking.tracks if getattr(t, 'select', False)]
    if not selected:
        print("[Kaiserlich Tracker] track_forward: Keine selektierten Tracks.")
        return False

    window, area, region, space = _find_clip_editor_area(clip)
    override_possible = all([window, area, region, space])

    print(f"[Kaiserlich Tracker] track_forward: Starte Tracking (tracks={len(selected)} sequence={sequence} backwards={backwards} override={override_possible})")

    try:
        if override_possible:
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                res = bpy.ops.clip.track_markers(backwards=backwards, sequence=sequence)
        else:
            res = bpy.ops.clip.track_markers(backwards=backwards, sequence=sequence)
    except Exception as e:  # noqa
        print(f"[Kaiserlich Tracker] track_forward: Fehler beim Tracking: {e}")
        return False

    if 'CANCELLED' in res:
        print("[Kaiserlich Tracker] track_forward: Blender meldet CANCELLED.")
        return False

    print(f"[Kaiserlich Tracker] track_forward: Tracking Operator Ergebnis={res}")
    return True

__all__ = [
    'track_forward_selected_markers',
]
