from .process_marker_path import get_track_segments, _iter_tracks

def _last_keyed_or_last_marker_frame(track):
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    return max(keyed) if keyed else max((m.frame for m in track.markers), default=None)

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True, also_track_bounds=True):
    """
    Entfernt (oder mutet nicht – hier immer *entfernen*) Marker genau auf Segmentgrenzen.
    - only_if_keyed=True: nur wenn Marker 'keyed' ist
    - also_track_bounds=True: zusätzlich min/max-Frame des Tracks als Grenze behandeln
    """
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue
        segs = get_track_segments(track)
        if not segs:
            continue

        frames_in_track = [m.frame for m in track.markers]
        if not frames_in_track:
            continue

        boundary_frames = set()
        for s, e in segs:
            boundary_frames.add(s)
            boundary_frames.add(e)
        if also_track_bounds:
            boundary_frames.add(min(frames_in_track))
            boundary_frames.add(max(frames_in_track))

        to_delete = []
        for f in boundary_frames:
            m = track.markers.find_frame(f)
            if not m:
                continue
            if only_if_keyed and not getattr(m, "is_keyed", False):
                continue
            to_delete.append(f)

        for f in to_delete:
            track.markers.delete_frame(f)

def prune_outside_segments(track_or_tracks, scene_end=None, action="mute"):
    """
    Marker entfernen/muten, die NICHT in Segmenten mit Länge >= 2 liegen
    oder hinter dem letzten gültigen Segment liegen.
    """
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        segs = get_track_segments(track)
        if not segs:
            continue

        # gültig: nur Segmente mit >=2 Frames
        valid_frames = set()
        for s, e in segs:
            if (e - s + 1) >= 2:
                valid_frames.update(range(s, e + 1))

        last_valid_end = max((e for s, e in segs if (e - s + 1) >= 2), default=None)

        def invalid(f):
            if f not in valid_frames:
                return True
            if last_valid_end is not None and f > last_valid_end:
                return True
            return False

        if action == "delete":
            frames = [m.frame for m in track.markers if invalid(m.frame)]
            for f in frames:
                track.markers.delete_frame(f)
        else:
            for m in track.markers:
                if invalid(m.frame):
                    m.mute = True

def mute_invalid_segments(track_or_tracks, scene_end=None, action="mute"):
    """
    Komfortfunktion: 'außerhalb' der gültigen Segmente muten/entfernen.
    """
    prune_outside_segments(track_or_tracks, scene_end=scene_end, action=action)
