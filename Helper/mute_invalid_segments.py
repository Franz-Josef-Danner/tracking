from .process_marker_path import get_unmuted_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def remove_segment_boundary_keys(track_or_tracks, delete_start=False, delete_end=True):
    """
    Löscht *explizit* Keyframes genau auf Segmentgrenzen.
    - delete_end=True: letzte Frame-Keys je Segment löschen (wichtig gegen 'estimated' nach Sequenzende)
    - delete_start=False: Start-Keys in Ruhe lassen (typisch sicherer)
    """
    removed = 0
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue
        segs = get_unmuted_segments(track)
        for (start, end) in segs:
            frames = []
            if delete_start:
                frames.append(start)
            if delete_end:
                frames.append(end)
            for f in frames:
                m = track.markers.find_frame(f)
                if m and getattr(m, "is_keyed", False):
                    track.markers.delete_frame(f)
                    removed += 1
    return removed


def prune_outside_segments(track_or_tracks, guard_before=1, guard_after=1, action="mute"):
    """
    Entfernt Marker *außerhalb* aller Segmente.
    - Vor dem ersten Segment: bis inkl. (first_start - guard_before)
    - Nach dem letzten Segment: ab (last_end + guard_after)
    - In *internen Lücken*: komplette Lücke ohne Puffer.

    action: "mute" oder "delete"
    Gibt (muted_count, deleted_count) zurück.
    """
    total_muted = 0
    total_deleted = 0

    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        segs = get_unmuted_segments(track)
        if not segs:
            continue

        # Segmentgrenzen sortiert
        segs = sorted(segs, key=lambda t: t[0])
        first_start = segs[0][0]
        last_end = segs[-1][1]

        # Bereiche definieren
        left_limit = first_start - guard_before
        right_limit = last_end + guard_after

        # Schneller Lookup: ist Frame in einem Segment?
        def in_any_segment(f):
            for (s, e) in segs:
                if s <= f <= e:
                    return True
            return False

        # Marker bewerten
        to_delete = []
        to_mute = []
        for m in track.markers:
            f = m.frame

            # Vor dem ersten Segment (mit Puffer)
            if f <= left_limit:
                (to_delete if action == "delete" else to_mute).append(m)
                continue

            # Nach dem letzten Segment (mit Puffer)
            if f >= right_limit:
                (to_delete if action == "delete" else to_mute).append(m)
                continue

            # Dazwischen: Segment oder Lücke?
            if in_any_segment(f):
                # drin -> behalten
                continue
            else:
                # interne Lücke -> komplett weg (kein Puffer)
                (to_delete if action == "delete" else to_mute).append(m)

        if action == "delete":
            # sicher löschen (erst Frames sammeln)
            frames = [m.frame for m in to_delete]
            for f in frames:
                track.markers.delete_frame(f)
            total_deleted += len(frames)
        else:
            for m in to_mute:
                if not getattr(m, "mute", False):
                    m.mute = True
                    total_muted += 1

    return total_muted, total_deleted
