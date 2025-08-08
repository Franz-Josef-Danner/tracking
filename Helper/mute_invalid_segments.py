from .process_marker_path import get_track_segments, _iter_tracks

def _last_keyed_frame(track):
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    return max(keyed) if keyed else None

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True, also_track_bounds=True):
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
    """Alles außerhalb gültiger Segmente ODER hinter letztem Keyframe muten/löschen."""
    total_muted = total_deleted = 0

    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        segs = get_track_segments(track)
        if not segs:
            continue

        # gültig = nur Segmente mit >=2 Frames
        valid_frames = set()
        for s, e in segs:
            if (e - s + 1) >= 2:
                valid_frames.update(range(s, e + 1))

        last_valid_end = max((e for s, e in segs if (e - s + 1) >= 2), default=None)
        last_keyed = _last_keyed_frame(track)
        hard_stop = last_keyed if last_keyed is not None else last_valid_end

        # Marker auswählen, die raus sollen
        if action == "delete":
            frames = [m.frame for m in track.markers
                      if (m.frame not in valid_frames) or (hard_stop is not None and m.frame > hard_stop)]
            for f in frames:
                track.markers.delete_frame(f)
            total_deleted += len(frames)
        else:
            for m in track.markers:
                f = m.frame
                if (f not in valid_frames) or (hard_stop is not None and f > hard_stop):
                    m.mute = True
                    total_muted += 1

    return total_muted, total_deleted

def mute_invalid_segments(track_or_tracks, scene_end=None, action="mute"):
    return prune_outside_segments(track_or_tracks, scene_end=scene_end, action=action)
