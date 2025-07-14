"""Find a frame with fewer tracking markers than a given minimum."""


def find_sparse_frame(clip, min_marker_count):
    frame_marker_count = {}
    for track in clip.tracking.tracks:
        for marker in track.markers:
            frame_marker_count[marker.frame] = frame_marker_count.get(marker.frame, 0) + 1
    for frame, count in sorted(frame_marker_count.items()):
        if count < min_marker_count:
            return frame
    return None
