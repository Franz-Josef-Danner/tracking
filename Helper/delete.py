import bpy


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks.

    Entspricht sinngemäß:
        marker = some_marker
        track = marker.track
        track.markers.delete_frame(marker.frame)

    Args:
        track_name: Name des Tracks
        frame: Frame-Nummer des zu löschenden Markers

    Returns:
        bool: True wenn Marker existierte und gelöscht wurde, sonst False.
    """
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] delete_marker_frame: Kein CLIP_EDITOR Kontext.")
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker] delete_marker_frame: Kein aktiver Clip.")
        return False
    tracking = clip.tracking
    try:
        for tr in tracking.tracks:
            if tr.name == track_name:
                marker = tr.markers.find_frame(frame)
                if marker is None:
                    print(f"[Kaiserlich Tracker] Marker nicht gefunden: track={track_name} frame={frame}")
                    return False
                tr.markers.delete_frame(frame)
                print(f"[Kaiserlich Tracker] Marker gelöscht: track={track_name} frame={frame}")
                return True
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Löschen Marker track={track_name} frame={frame}: {e}")
    return False
