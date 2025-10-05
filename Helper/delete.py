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

def delete_track_by_name(context, track_name: str) -> bool:
    """Löscht den GESAMTEN Track (inkl. aller Marker) anhand seines Namens.

    Rückgabe True wenn gelöscht, sonst False.
    """
    tracking = _get_tracking(context)
    if tracking is None:
        return False
    tracks = tracking.tracks
    track = tracks.get(track_name)
    if track is None:
        return False
    try:
        tracks.remove(track)
        print(f"[Kaiserlich Tracker] delete: Track '{track_name}' entfernt (kompletter Track gelöscht).")
        return True
    except Exception as e:  # noqa
        print(f"[Kaiserlich Tracker] delete: Fehler beim Entfernen von '{track_name}': {e}")
        return False

def delete_tracks_by_names(context, track_names: Iterable[str]) -> int:
    """Löscht mehrere komplette Tracks.

    Rückgabe: Anzahl erfolgreich entfernter Tracks.
    """
    tracking = _get_tracking(context)
    if tracking is None:
        return 0
    tracks = tracking.tracks
    removed = 0
    # Um Mehrfachnamen zu vermeiden, Liste materialisieren + unique
    unique: List[str] = list(dict.fromkeys(track_names))
    for name in unique:
        track = tracks.get(name)
        if track is None:
            continue
        try:
            tracks.remove(track)
            removed += 1
            print(f"[Kaiserlich Tracker] delete: Track '{name}' entfernt.")
        except Exception as e:  # noqa
            print(f"[Kaiserlich Tracker] delete: Fehler beim Entfernen von '{name}': {e}")
    print(f"[Kaiserlich Tracker] delete: {removed} Tracks insgesamt gelöscht.")
    return removed
