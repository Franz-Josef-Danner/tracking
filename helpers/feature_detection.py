# Feature detection helper functions
import bpy
from .feature_math import (
    calculate_base_values,
    marker_target_conservative,
)
from .utils import (
    compute_detection_params,
    jump_to_frame_with_few_markers,
)


def find_next_low_marker_frame(scene, clip, marker_threshold: int):
    """Return ``(frame, count)`` for the first frame below ``marker_threshold``."""
    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.tracks:
            marker = track.markers.find_frame(frame)
            if marker and not marker.mute and marker.co.length_squared != 0.0:
                count += 1
        if count < marker_threshold:
            return frame, count
    return None, 0


def find_low_marker_frame(clip, threshold):
    """Return the first frame with fewer markers than ``threshold``."""
    scene = bpy.context.scene
    return find_next_low_marker_frame(scene, clip, threshold)


def jump_to_first_frame_with_few_active_markers(min_required=5):
    scene = bpy.context.scene
    clip = bpy.context.space_data.clip
    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.tracks:
            if track.name.startswith('GOOD_'):
                marker = track.markers.find_frame(frame)
                if marker and not marker.mute and marker.co.length_squared != 0.0:
                    count += 1
        if count < min_required:
            jump_to_frame_with_few_markers(
                clip,
                min_marker_count=min_required,
                start_frame=frame,
                end_frame=frame,
            )
            from .tracking_helpers import _update_nf_and_motion_model

            _update_nf_and_motion_model(frame, clip)
            return frame
    return None


def detect_features_once(context=None, clip=None, threshold=None):
    """Run feature detection if available."""
    if context is None:
        context = bpy.context
    if clip is None:
        clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("\u26a0\ufe0f Kein aktiver Movie Clip gefunden.")
        return
    if threshold is None:
        threshold = context.scene.tracker_threshold
    if bpy.ops.clip.detect_features.poll():
        width, _ = clip.size
        if width == 0:
            print("\u26a0\ufe0f Clipgr\u00f6\u00dfe ist 0 - Detect abgebrochen")
            return
        margin_base, min_distance_base = calculate_base_values(width)
        detection_threshold, margin, min_distance = compute_detection_params(
            threshold, margin_base, min_distance_base
        )
        if bpy.ops.clip.proxy_off.poll():
            bpy.ops.clip.proxy_off()
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=margin,
            min_distance=min_distance,
        )


def detect_features_main(context, clip, threshold):
    """Run feature detection with the aggressive marker target."""
    target = marker_target_conservative(context.scene.marker_frame) * 3
    detect_features_once(context=context, clip=clip, threshold=threshold)
    return target


def detect_features_test(context, clip, threshold):
    """Run feature detection with the conservative marker target."""
    target = marker_target_conservative(context.scene.marker_frame)
    detect_features_once(context=context, clip=clip, threshold=threshold)
    return target
