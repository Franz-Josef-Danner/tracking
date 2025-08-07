from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def _last_keyed_or_last_marker_frame(track):
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    if keyed:
        return max(keyed)
    all_frames = [m.frame for m in track.markers]
    return max(all_frames) if all_frames else None

def mute_invalid_segments(track_or_tracks, scene_end, action="mute"):
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        # --- 1) normale Segment-Logik (jetzt basierend auf Keyframes) ---
        segments = get_track_segments(track)
        if not segments:
            continue
        segments = sorted(segments, key=lambda se: se[0])

        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        first_frame = min((m.frame for m in track.markers), default=None)
        last_valid_by_segments = max(end for _, end in segments)

        # --- 2) Safety: last_keyed als harte Obergrenze für "gültig" ---
        last_keyed = _last_keyed_or_last_marker_frame(track)
        if last_keyed is not None:
            last_valid_frame = min(last_valid_by_segments, last_keyed)
        else:
            last_valid_frame = last_valid_by_segments

        if action == "delete":
            to_delete = []
            for m in track.markers:
                f = m.frame
                if (first_frame is not None and f == first_frame) or (f not in valid_frames) or (f > last_valid_frame):
                    to_delete.append(f)
            for f in to_delete:
                track.markers.delete_frame(f)
        else:
            for m in track.markers:
                f = m.frame
                if (first_frame is not None and f == first_frame) or (f not in valid_frames) or (f > last_valid_frame):
                    m.mute = True
