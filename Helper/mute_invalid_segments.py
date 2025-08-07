# Helper/mute_invalid_segments.py
from .process_marker_path import get_track_segments

__all__ = ["mute_invalid_segments", "remove_segment_boundary_keys"]

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def remove_segment_boundary_keys(track):
    """
    Löscht Keyframes genau am Segment-Start/-Ende sowie am globalen Track-Start/-Ende.
    """
    segments = get_track_segments(track)
    if not segments or not getattr(track, "markers", None):
        return

    # Kandidaten sammeln: Segment-Grenzen + globaler Track-Anfang/-Ende
    frames_to_check = set()
    for start, end in segments:
        frames_to_check.update((start, end))

    all_frames = [m.frame for m in track.markers]
    if all_frames:
        frames_to_check.add(min(all_frames))
        frames_to_check.add(max(all_frames))

    # Nur harte Keyframes an genau diesen Frames löschen
    for f in sorted(frames_to_check):
        m = track.markers.find_frame(f)
        if m and getattr(m, "is_keyed", False):
            track.markers.delete_frame(f)

def mute_invalid_segments(track_or_tracks, scene_end=None, action="mute"):
    """
    - Keyframes an Segmentgrenzen zuerst *löschen* (Hard stop)
    - Danach: nur Segmente >=2 Frames gelten als gültig
    - Alles außerhalb → mute oder delete
    - Nach letztem *Keyframe* wird ebenfalls gemutet/gelöscht
    """
    for track in _iter_tracks(track_or_tracks):
        if not getattr(track, "markers", None):
            continue

        # 1) Grenz-Keyframes immer entfernen
        remove_segment_boundary_keys(track)

        # 2) Segmente nach dem Entfernen neu bilden
        segments = get_track_segments(track)
        if not segments:
            continue

        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        # Harte Obergrenze: letztes Keyframe (falls vorhanden)
        keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
        last_keyed = max(keyed) if keyed else None

        def is_invalid(m):
            f = m.frame
            if f not in valid_frames:
                return True
            if last_keyed is not None and f > last_keyed:
                return True
            return False

        if action == "delete":
            # vorsichtig: erst sammeln, dann löschen
            to_delete = [m.frame for m in list(track.markers) if is_invalid(m)]
            for f in sorted(set(to_delete)):
                track.markers.delete_frame(f)
        else:
            for m in track.markers:
                if is_invalid(m):
                    m.mute = True
