# Helper/filter_and_delete_tracks.py
# Kaiserlich Tracker – selektives Filter/Delete nur für neue Tracks

import bpy
from typing import Iterable, List, Tuple, Optional, Dict

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


def _snapshot_selection(tracking: bpy.types.MovieTracking) -> Dict[str, bool]:
    """Speichert den Auswahlzustand aller Tracks."""
    return {t.name: bool(getattr(t, "select", False)) for t in tracking.tracks}


def _restore_selection(tracking: bpy.types.MovieTracking, sel_map: Dict[str, bool]) -> None:
    """Stellt eine vorherige Track-Selektion wieder her."""
    for t in tracking.tracks:
        try:
            t.select = bool(sel_map.get(t.name, False))
        except Exception:
            pass


def _select_only(tracking: bpy.types.MovieTracking, names: Iterable[str]) -> None:
    """Selektiert ausschließlich die angegebenen Track-Namen."""
    name_set = set(names or [])
    for t in tracking.tracks:
        t.select = (t.name in name_set)


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def filter_and_delete_tracks(
    include_names: Iterable[str],
    *,
    threshold: float = 30.0,
    clip: Optional[bpy.types.MovieClip] = None,
) -> Tuple[List[str], int]:
    """
    Führt das Blender-Filtering **nur** für die angegebenen Track-Namen aus
    und löscht ausschließlich die dabei als 'problematisch' markierten Tracks
    innerhalb dieser Whitelist.

    Parameter:
        include_names: Iterable[str] – Liste der neuen Track-Namen
        threshold: float – Filter-Threshold für bpy.ops.clip.filter_tracks
        clip: Optional[MovieClip] – Clip, auf dem gearbeitet wird

    Rückgabe:
        (deleted_names, deleted_count)
    """
    include_set = set([n for n in (include_names or []) if isinstance(n, str) and n.strip()])
    if not include_set:
        return ([], 0)

    tracking = _get_tracking(clip)
    if tracking is None or not getattr(tracking, "tracks", None):
        return ([], 0)

    # Nur Tracks, die tatsächlich existieren
    existing_names = {t.name for t in tracking.tracks}
    include_set &= existing_names
    if not include_set:
        return ([], 0)

    # CLIP_EDITOR-Context für Operator-Execution
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

    # Ursprüngliche Selektion sichern
    sel_snapshot = _snapshot_selection(tracking)

    try:
        # Nur neue Tracks selektieren
        _select_only(tracking, include_set)
        # Filter ausführen – Nutzung des neuen Context-Override-API (Blender ≥ 3.x)
        try:
            with bpy.context.temp_override(
                window=window,
                area=area,
                region=region,
                space_data=space,
            ):
                result = bpy.ops.clip.filter_tracks(track_threshold=float(threshold))
                if result != {'FINISHED'}:
                    print(f"[Helper][FilterDelete] ⚠️ bpy.ops.clip.filter_tracks result={result}")
        except Exception as ex:
            raise RuntimeError(f"clip.filter_tracks Context-Fehler: {ex!r}")

        # Nach Filter: Blender markiert problematische Tracks mit select=True
        flagged_names = [t.name for t in tracking.tracks if t.select]

        # Nur problematische Tracks, die auch in include_set sind
        names_to_delete = [n for n in flagged_names if n in include_set]

        if not names_to_delete:
            return ([], 0)

        # Löschen der problematischen Tracks

        deleted_count = delete_tracks_by_names(bpy.context, names_to_delete)

        return (names_to_delete, int(deleted_count))

    finally:
        # Ursprüngliche Selektion wiederherstellen
        _restore_selection(tracking, sel_snapshot)
