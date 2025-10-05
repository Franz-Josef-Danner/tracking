import bpy
from typing import Iterable, List, Optional

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

def _direct_remove(tracks, track) -> bool:
    """Versucht direkten remove-Aufruf, falls Collection dies unterstützt."""
    if hasattr(tracks, "remove"):
        try:
            tracks.remove(track)
            return True
        except Exception as e:  # noqa
            print(f"[Kaiserlich Tracker] delete: direct remove fehlgeschlagen: {e}")
    else:
        print("[Kaiserlich Tracker] delete: tracks.remove nicht verfügbar – versuche Operator-Fallback.")
    return False

def _operator_remove(context, track) -> bool:
    """Fallback: Track per Operator entfernen (benötigt richtigen Clip-Editor Kontext).
    Versucht mehrere mögliche Operatornamen (API Unterschiede)."""
    # Auswahl setzen
    tracking = _get_tracking(context)
    if tracking is None:
        return False
    tracks = tracking.tracks
    for t in tracks:
        try:
            t.select = False
        except Exception:
            pass
    try:
        track.select = True
    except Exception:
        pass

    candidates = [
        "clip.delete_track",            # wahrscheinlich (X im Clip Editor)
        "clip.tracking_track_delete",   # mögliche Variante
        "clip.track_remove",            # fallback Name geraten
    ]
    for op in candidates:
        if not hasattr(bpy.ops.clip, op.split('.')[-1]):
            continue
        try:
            res = bpy.ops.clip.__getattribute__(op.split('.')[-1])()
            if 'CANCELLED' not in res:
                return True
        except Exception:
            continue
    return False

def delete_track_by_name(context, track_name: str) -> bool:
    """Löscht den GESAMTEN Track (inkl. aller Marker) anhand seines Namens.

    Reihenfolge:
      1. Direkter remove-Aufruf (schnell, wenn API unterstützt)
      2. Operator-Fallback (benötigt passenden Kontext)

    Rückgabe True wenn gelöscht, sonst False.
    """
    tracking = _get_tracking(context)
    if tracking is None:
        return False
    tracks = tracking.tracks
    track = tracks.get(track_name)
    if track is None:
        return False

    if _direct_remove(tracks, track):
        print(f"[Kaiserlich Tracker] delete: Track '{track_name}' per direct remove gelöscht.")
        return True
    # Operator-Fallback
    if _operator_remove(context, track):
        print(f"[Kaiserlich Tracker] delete: Track '{track_name}' per Operator gelöscht.")
        return True

    print(f"[Kaiserlich Tracker] delete: Track '{track_name}' konnte nicht gelöscht werden.")
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
