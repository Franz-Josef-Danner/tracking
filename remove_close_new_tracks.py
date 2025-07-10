"""Utility: delete NEU_ tracks too near GOOD_ tracks."""

import bpy
import math
import mathutils


def remove_close_new_tracks(context, clip, base_distance, threshold):
    """Delete ``NEU_`` tracks too close to existing ``GOOD_`` markers."""

    current_frame = context.scene.frame_current
    tracks = clip.tracking.tracks

    neu_tracks = [t for t in tracks if t.name.startswith("NEU_")]
    existing = [t for t in tracks if t.name.startswith("GOOD_")]

    # Filter existing tracks to those with a marker at the current frame
    good_tracks = []
    missing = 0
    for track in existing:
        marker = track.markers.find_frame(current_frame)
        if marker:
            good_tracks.append((track, marker))
        else:
            missing += 1
    if missing:
        pass

    if not neu_tracks or not good_tracks:
        return 0

    scale = math.log10(threshold * 100000) / 5
    scaled_dist = max(1, int(base_distance * scale))
    norm_dist = (scaled_dist / 2.0) / clip.size[0]

    to_remove = []
    for neu in neu_tracks:
        neu_marker = neu.markers.find_frame(current_frame)
        if not neu_marker:
            if context.scene.cleanup_verbose:
                pass
            continue
        neu_pos = mathutils.Vector(neu_marker.co)
        for good, good_marker in good_tracks:
            good_pos = mathutils.Vector(good_marker.co)
            dist = (neu_pos - good_pos).length
            if context.scene.cleanup_verbose:
                pass
            if dist < norm_dist:
                to_remove.append(neu)
                break

    if not to_remove:
        return 0

    for t in tracks:
        t.select = False
    for t in to_remove:
        t.select = True

    area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if area:
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        space = getattr(area, 'spaces', None)
        space = space.active if space else None
        if region and space:
            with context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.delete_track()

    print(f"[Cleanup] Removed {len(to_remove)} NEU_ tracks")
    return len(to_remove)

