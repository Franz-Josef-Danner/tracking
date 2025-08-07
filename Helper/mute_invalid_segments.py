from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def mute_invalid_segments(track_or_tracks, scene_end, action="mute"):
    """
    action: "mute" oder "delete"
    - alles was NICHT zu einem Segment (>=2 Frames) gehört → weg/mute
    - erster Marker im Track → weg/mute
    - alles NACH letztem gültigen Segment → weg/mute
    """
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        segments = get_track_segments(track)
        if not segments:
            continue
        segments = sorted(segments, key=lambda se: se[0])

        # Nur Segmente mit Länge >= 2 gelten als "valid"
        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        first_frame = min((m.frame for m in track.markers), default=None)
        last_valid_frame = max(end for _, end in segments)

        if action == "delete":
            to_delete = []
            for m in track.markers:
                f = m.frame
                if (first_frame is not None and f == first_frame) or (f not in valid_frames) or (f > last_valid_frame):
                    to_delete.append(f)
            for f in to_delete:
                track.markers.delete_frame(f)
        else:  # "mute"
            for m in track.markers:
                f = m.frame
                if (first_frame is not None and f == first_frame) or (f not in valid_frames) or (f > last_valid_frame):
                    m.mute = True
