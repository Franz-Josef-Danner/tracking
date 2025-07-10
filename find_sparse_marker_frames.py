"""Utility: return frames with sparse marker counts."""

import bpy


def find_sparse_marker_frames(clip, threshold):
    """Return list of frames with fewer markers than ``threshold``."""

    if clip is None:
        clip = bpy.context.space_data.clip
        if not clip:
            return []

    scene = bpy.context.scene
    start = int(scene.frame_start)
    end = int(scene.frame_end)
    frames_with_few_markers = []
    for frame in range(start, end):
        count = 0
        for track in clip.tracking.tracks:
            marker = track.markers.find_frame(frame)
            if marker and not marker.mute:
                count += 1
        if count < threshold:
            frames_with_few_markers.append((frame, count))
    return frames_with_few_markers


