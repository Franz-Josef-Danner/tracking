import bpy
from typing import Iterable, List

def _get_tracking(context):
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        print("[Kaiserlich Tracker] delete: Kein Clip aktiv – Abbruch.")
        return None
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("[Kaiserlich Tracker] delete: Kein tracking Objekt – Abbruch.")
        return None
    return tracking

def _find_clip_editor_area(clip):
    """Sucht eine passende CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        # Wenn Clip gesetzt, bevorzugt passenden
                        if getattr(space, 'clip', None) == clip or space.clip is None:
                            # Nehme erste Region mit WINDOW
                            region_window = None
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    region_window = region
                                    break
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None

def _operator_delete_selected(window, area, region, space) -> bool:
    """Führt den eigentlichen Operator im Override-Kontext aus."""
    try:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            # Primär bekannter Operator
            if hasattr(bpy.ops.clip, 'delete_track'):
                res = bpy.ops.clip.delete_track()
                return 'CANCELLED' not in res
            # Fallback Namen probieren
            for name in ['tracking_track_delete', 'track_remove']:
                if hasattr(bpy.ops.clip, name):
                    res = getattr(bpy.ops.clip, name)()
                    if 'CANCELLED' not in res:
                        return True
    except Exception as e:  # noqa
        print(f"[Kaiserlich Tracker] delete: Operator-Ausführung fehlgeschlagen: {e}")
    return False

def delete_track_by_name(context, track_name: str) -> bool:
    """Löscht einen kompletten Track (alle Marker) über Operator-Selektion."""
    return delete_tracks_by_names(context, [track_name]) == 1

def delete_tracks_by_names(context, track_names: Iterable[str]) -> int:
    """Löscht mehrere komplette Tracks per Operator in einem Rutsch.

    Vorgehen:
      - Alle Tracks des Clips holen
      - Auswahl leeren
      - Nur gewünschte Tracks select=True setzen
      - Einmal Operator aufrufen
    Rückgabe: Anzahl der tatsächlich entfernten Tracks (Heuristik über vorher/nachher Zählung).
    """
    tracking = _get_tracking(context)
    if tracking is None:
        return 0
    clip = bpy.context.space_data.clip if getattr(bpy.context, 'space_data', None) else None
    tracks = tracking.tracks

    unique: List[str] = list(dict.fromkeys(track_names))
    targets = []
    for name in unique:
        tr = tracks.get(name)
        if tr is not None:
            targets.append(tr)
    if not targets:
        return 0

    # Auswahl zurücksetzen
    for tr in tracks:
        try:
            tr.select = False
        except Exception:
            pass
    # Auswahl setzen
    for tr in targets:
        try:
            tr.select = True
        except Exception:
            pass

    before = len(tracks)
    window, area, region, space = _find_clip_editor_area(clip)
    if not window:
        print("[Kaiserlich Tracker] delete: Kein CLIP_EDITOR Kontext gefunden – bitte Fenster öffnen.")
        return 0
    if not _operator_delete_selected(window, area, region, space):
        print("[Kaiserlich Tracker] delete: Operator konnte Tracks nicht löschen.")
        return 0
    after = len(tracks)
    removed = max(0, before - after)
    print(f"[Kaiserlich Tracker] delete: {removed} Tracks gelöscht (Ziel: {len(targets)}).")
    return removed
