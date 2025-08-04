import bpy
import math
from .cleanup import clean_tracks


def _adaptive_detect(clip, markers_per_frame, base_threshold):
    """Suche Marker mit logarithmisch steigendem Threshold."""
    tracking = clip.tracking
    image_width = float(clip.size[0])
    min_distance = int(image_width * 0.05)
    count_new = 0
    step = 0
    while count_new < markers_per_frame:
        threshold = base_threshold * (1 + math.log(step + 1, 2))
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=16,
            threshold=threshold,
            min_distance=min_distance,
        )
        new_tracks = [t for t in tracking.tracks if t.select]
        count_new = len(new_tracks)
        step += 1
        if step > 10:
            break
    return count_new


def _frame_coverage_analysis(context, markers_per_frame, threshold):
    """Analysiert Marker pro Frame und füllt unterversorgte Frames auf."""
    scene = context.scene
    clip = context.space_data.clip
    tracking_obj = clip.tracking.objects.active
    start = clip.frame_start
    end = start + clip.frame_duration
    counts = {f: 0 for f in range(start, end)}
    for track in tracking_obj.tracks:
        for m in track.markers:
            if not m.mute:
                counts[m.frame] += 1
    needed = [f for f, c in counts.items() if c < markers_per_frame]
    image_width = float(clip.size[0])
    min_distance = int(image_width * 0.05)
    for f in needed:
        scene.frame_current = f
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=16,
            threshold=threshold,
            min_distance=min_distance,
        )
    return needed


def run_tracking(context, markers_per_frame, min_frames, error_limit, max_attempts=3):
    """Führt adaptives Tracking mit Wiederholungen durch."""
    clip = context.space_data.clip
    tracking = clip.tracking
    settings = tracking.settings
    image_width = float(clip.size[0])
    settings.default_pattern_size = max(int(image_width / 100), 5)
    settings.default_search_size = settings.default_pattern_size
    settings.default_motion_model = "Loc"
    settings.default_pattern_match = "KEYFRAME"
    settings.default_correlation_min = 0.9

    threshold = 0.5
    for attempt in range(max_attempts):
        bpy.ops.clip.select_all(action="DESELECT")
        _adaptive_detect(clip, markers_per_frame, threshold)
        clean_tracks(tracking.objects.active, min_frames, error_limit)
        if len(tracking.objects.active.tracks) >= markers_per_frame:
            break
        threshold *= 1.5
    _frame_coverage_analysis(context, markers_per_frame, threshold)


__all__ = ["run_tracking"]
