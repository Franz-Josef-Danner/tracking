import bpy
from typing import Optional

def delete_track(context, track_name: str) -> bool:
    """Löscht einen gesamten Track (neu erzeugter Marker-Track) sicher.

    Returns:
        bool: True wenn entfernt, sonst False.
    """
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print(f"[Kaiserlich Tracker] delete_track: Kein CLIP_EDITOR Kontext.")
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        print(f"[Kaiserlich Tracker] delete_track: Kein aktiver Clip.")
        return False
    tracking = clip.tracking
    try:
        for tr in list(tracking.tracks):
            if tr.name == track_name:
                tracking.tracks.remove(tr)
                print(f"[Kaiserlich Tracker] Track gelöscht: {track_name}")
                return True
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Löschen von {track_name}: {e}")
    return False
