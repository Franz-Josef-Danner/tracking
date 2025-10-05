import bpy

def delete_track_by_name(context, track_name: str) -> bool:
    """Löscht einen Track (und damit alle Marker dieses Tracks) anhand seines Namens.

    Rückgabe True wenn gelöscht, sonst False.
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        print("[Kaiserlich Tracker] delete: Kein Clip aktiv – Abbruch.")
        return False
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("[Kaiserlich Tracker] delete: Kein tracking Objekt – Abbruch.")
        return False

    tracks = tracking.tracks
    track = tracks.get(track_name)
    if track is None:
        # Bereits entfernt oder nie vorhanden
        return False
    try:
        tracks.remove(track)
        print(f"[Kaiserlich Tracker] delete: Track '{track_name}' entfernt.")
        return True
    except Exception as e:  # noqa
        print(f"[Kaiserlich Tracker] delete: Fehler beim Entfernen von '{track_name}': {e}")
        return False
