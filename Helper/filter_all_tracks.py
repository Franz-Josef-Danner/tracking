# Helper/filter_all_tracks.py
# Kaiserlich Tracker – globales Filter/Delete für alle Tracks

import bpy
from typing import List, Tuple, Optional

from .find_clip_editor_area import find_clip_editor_area
from .delete import delete_tracks_by_names


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_tracking(clip: Optional[bpy.types.MovieClip]):
    """Gibt das Tracking-Objekt eines Clips zurück, falls vorhanden."""
    if clip and getattr(clip, "tracking", None):
        return clip.tracking
    space_clip = getattr(getattr(bpy.context, "space_data", None), "clip", None)
    if space_clip and getattr(space_clip, "tracking", None):
        return space_clip.tracking
    return None


def _snapshot_selection(tracking: bpy.types.MovieTracking):
    """Speichert den Auswahlzustand aller Tracks."""
    return {t.name: bool(getattr(t, "select", False)) for t in tracking.tracks}


def _restore_selection(tracking: bpy.types.MovieTracking, sel_map: dict) -> None:
    """Stellt eine vorherige Track-Selektion wieder her."""
    for t in tracking.tracks:
        try:
            t.select = bool(sel_map.get(t.name, False))
        except Exception:
            pass


def _select_all(tracking: bpy.types.MovieTracking) -> None:
    """Selektiert alle Tracks."""
    for t in tracking.tracks:
        t.select = True


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def filter_and_delete_all_tracks(
    *,
    threshold: float = 30.0,
    clip: Optional[bpy.types.MovieClip] = None,
) -> Tuple[List[str], int]:
    """
    Führt das Blender-Filtering **für alle vorhandenen Tracks** aus
    und löscht anschließend alle vom Filter markierten Tracks.

    Parameter:
        threshold: float – Filter-Threshold für bpy.ops.clip.filter_tracks
        clip: Optional[MovieClip] – Clip, auf dem gearbeitet wird

    Rückgabe:
        (deleted_names, deleted_count)
    """
    tracking = _get_tracking(clip)
    if tracking is None or not getattr(tracking, "tracks", None):
        print("[Helper][FilterAll] ⚠️ Kein Tracking-Objekt oder keine Tracks vorhanden.")
        return ([], 0)

    # CLIP_EDITOR-Kontext für Operator
    window, area, region, space = find_clip_editor_area(clip)
    if not window:
        raise RuntimeError("Keine CLIP_EDITOR Area gefunden – filter_tracks benötigt gültigen Kontext.")

    override = {
        "window": window,
        "screen": window.screen,
        "area": area,
        "region": region,
        "space_data": space,
    }

    # Selektion sichern
    sel_snapshot = _snapshot_selection(tracking)

    try:
        # Alle Tracks selektieren
        _select_all(tracking)
        total = len(tracking.tracks)
        print(f"[Helper][FilterAll] ▶️ {total} Tracks für globalen Filter ausgewählt.")

        # Filter ausführen
        try:
            result = bpy.ops.clip.filter_tracks(override, track_threshold=float(threshold))
            if result != {'FINISHED'}:
                print(f"[Helper][FilterAll] ⚠️ bpy.ops.clip.filter_tracks result={result}")
        except TypeError as te:
            raise RuntimeError(f"clip.filter_tracks Parameterfehler: {te!r}")

        # Vom Filter markierte (selektierte) Tracks identifizieren
        flagged_names = [t.name for t in tracking.tracks if t.select]
        if not flagged_names:
            print("[Helper][FilterAll] Keine problematischen Tracks gefunden.")
            return ([], 0)

        # Löschen der markierten Tracks
        print(f"[Helper][FilterAll] 🔸 {len(flagged_names)} Tracks werden gelöscht: "
              f"{flagged_names[:5]}{' …' if len(flagged_names) > 5 else ''}")
        deleted_count = delete_tracks_by_names(bpy.context, flagged_names)
        print(f"[Helper][FilterAll] 🗑️ {deleted_count} Tracks gelöscht.")

        return (flagged_names, int(deleted_count))

    finally:
        _restore_selection(tracking, sel_snapshot)
        print("[Helper][FilterAll] ✅ Selektion wiederhergestellt.")
