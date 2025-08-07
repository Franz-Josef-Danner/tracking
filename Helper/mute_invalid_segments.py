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

        # Segmente AUS ALLEN FRAMES
        segments = get_track_segments(track)
        if not segments:
            continue

        # nur Segmente >=2 Frames als gültig werten
        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        # "Terminal keyed": Segment-Ende ist keyed UND es gibt KEINEN Marker bei end+1
        terminal_keyed = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                m_end = track.markers.find_frame(end)
                if m_end and getattr(m_end, "is_keyed", False):
                    if not track.markers.find_frame(end + 1):
                        terminal_keyed.add(end)

        first_frame = min((m.frame for m in track.markers), default=None)
        last_keyed = _last_keyed_or_last_marker_frame(track)  # harte Obergrenze

        def invalid(f):
            # 0) terminal keyed Frames gelten immer als ungültig
            if f in terminal_keyed:
                return True
            # 1) Isolierte/Einzelmarker raus
            if f not in valid_frames:
                return True
            # 2) Nach letztem KEYED-Frame raus (falls vorhanden)
            if last_keyed is not None and f > last_keyed:
                return True
            # 3) optional: ersten Marker raus
            # if first_frame is not None and f == first_frame:
            #     return True
            return False

        if action == "delete":
            to_delete = [m.frame for m in track.markers if invalid(m.frame)]
            # Sicherheit: terminal keyed IMMER löschen
            to_delete = sorted(set(to_delete).union(terminal_keyed))
            for f in to_delete:
                track.markers.delete_frame(f)
        else:
            # Bei mute: terminal keyed trotzdem hard-delete, damit 'estimated' sicher stoppt
            for f in sorted(terminal_keyed):
                track.markers.delete_frame(f)
            for m in track.markers:
                if invalid(m.frame):
                    m.mute = True
