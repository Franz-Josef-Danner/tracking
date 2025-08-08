# Helper/keyframe_ops.py

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def delete_all_keyframes(track_or_tracks):
    """
    Löscht ALLE keyframes (Marker mit is_keyed=True) in den gegebenen Tracks.
    Gibt die Anzahl gelöschter Marker zurück.
    """
    total = 0
    for t in _iter_tracks(track_or_tracks):
        if not hasattr(t, "markers") or not t.markers:
            continue
        # erst Frames sammeln, dann löschen (sonst Iterator invalid)
        frames = [m.frame for m in t.markers if getattr(m, "is_keyed", False)]
        for f in frames:
            if t.markers.find_frame(f):
                t.markers.delete_frame(f)
                total += 1
    return total
