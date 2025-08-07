from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def _last_keyed_or_last_marker_frame(track):
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    return max(keyed) if keyed else (max((m.frame for m in track.markers), default=None))

def mute_invalid_segments(track_or_tracks, scene_end, action="mute"):
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        # Segmente AUS ALLEN FRAMES (Fix #1)
        segments = get_track_segments(track)
        if not segments:
            continue

        # nur Segmente >=2 Frames als gültig werten
        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        first_frame = min((m.frame for m in track.markers), default=None)
        last_keyed = _last_keyed_or_last_marker_frame(track)  # harte Obergrenze

        def invalid(f):
            # 1) Isolierte/Einzelmarker raus
            if f not in valid_frames:
                return True
            # 2) Nach letztem KEYED-Frame raus (falls vorhanden)
            if last_keyed is not None and f > last_keyed:
                return True
            # 3) optional: explizit ersten Marker muten? -> ggf. auskommentieren
            # if first_frame is not None and f == first_frame:
            #     return True
            return False

        if action == "delete":
            to_delete = [m.frame for m in track.markers if invalid(m.frame)]
            for f in to_delete:
                track.markers.delete_frame(f)
        else:
            for m in track.markers:
                if invalid(m.frame):
                    m.mute = True
