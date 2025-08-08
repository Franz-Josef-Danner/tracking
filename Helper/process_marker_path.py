import bpy

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def process_marker_path(track, from_frame, direction, action="mute", mute=True):
    """
    Aktion auf Markern eines Tracks ab from_frame in 'forward'/'backward':
      - action='mute'   -> Marker.mute setzen
      - action='delete' -> Marker-Frames löschen
    """
    if not track or not hasattr(track, "markers") or not track.markers:
        return

    if direction == "forward":
        relevant = [m for m in track.markers if m.frame >= from_frame]
    elif direction == "backward":
        relevant = [m for m in track.markers if m.frame <= from_frame]
    else:
        return

    if action == "delete":
        frames_to_delete = [m.frame for m in relevant]
        for f in frames_to_delete:
            track.markers.delete_frame(f)
    else:
        for m in relevant:
            m.mute = bool(mute)

def get_track_segments(track):
    """
    Zusammenhängende Segmente (basierend auf ALLEN Markern des Tracks).
    Gibt Liste von (start, end) inkl. zurück.
    """
    if not hasattr(track, "markers") or not track.markers:
        return []
    frames = sorted(m.frame for m in track.markers)
    if not frames:
        return []
    segs = []
    s = p = frames[0]
    for f in frames[1:]:
        if f - p > 1:
            segs.append((s, p))
            s = f
        p = f
    segs.append((s, p))
    return segs

def get_unmuted_segments(track):
    """
    Segmente nur aus UNGEMUTETEN Markern (für spätere Prune-Logik).
    """
    if not hasattr(track, "markers") or not track.markers:
        return []
    frames = sorted(m.frame for m in track.markers if not getattr(m, "mute", False))
    if not frames:
        return []
    segs = []
    s = p = frames[0]
    for f in frames[1:]:
        if f - p > 1:
            segs.append((s, p))
            s = f
        p = f
    segs.append((s, p))
    return segs
