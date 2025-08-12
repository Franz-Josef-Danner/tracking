# Helper/mute_ops.py
from .segments import get_track_segments

def mute_marker_path(track, from_frame, direction, mute=True):
    try:
        markers = list(track.markers)  # Snapshot gegen Collection-Invalidation
    except Exception:
        return
    fcmp = (lambda f: f >= from_frame) if direction == 'forward' else (lambda f: f <= from_frame)
    for m in markers:
        try:
            if m and fcmp(m.frame):
                _ = m.co  # RNA-Validierung
                m.mute = bool(mute)
        except ReferenceError:
            continue
        except Exception:
            continue

def mute_after_last_marker(track, scene_end):
    segments = get_track_segments(track)
    if not segments:
        return
    last_valid_frame = segments[-1][-1]
    for m in track.markers:
        if last_valid_frame <= m.frame <= scene_end:
            m.mute = True

def mute_unassigned_markers(tracks):
    """Mute Marker, die nicht Teil eines ≥2-Frames-Segments sind oder exakt am Track-Anfang liegen."""
    for track in tracks:
        segments = get_track_segments(track)
        valid_frames = set()
        for segment in segments:
            if len(segment) >= 2:
                valid_frames.update(segment)
        if not track.markers:
            continue
        first_frame = min(m.frame for m in track.markers)
        for marker in track.markers:
            f = marker.frame
            if f not in valid_frames or f == first_frame:
                marker.mute = True
