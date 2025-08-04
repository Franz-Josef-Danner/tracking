import bpy
import math
import statistics
from .cleanup import clean_tracks

def _marker_counts(tracking_obj, start, end):
    """Zählt aktive Marker pro Frame."""
    counts = {f: 0 for f in range(start, end)}
    for track in tracking_obj.tracks:
        for m in track.markers:
            if not m.mute:
                counts[m.frame] += 1
    return counts


def _average_track_length(tracking_obj):
    """Berechnet die durchschnittliche Marker-Länge."""
    lengths = [len([m for m in t.markers if not m.mute]) for t in tracking_obj.tracks]
    return sum(lengths) / len(lengths) if lengths else 0.0


def _adaptive_detect(clip, markers_per_frame, base_threshold):
    """Suche Marker mit adaptivem Threshold."""
    print(
        f"Adaptive detect: markers_per_frame={markers_per_frame}, "
        f"base_threshold={base_threshold}"
    )
    tracking = clip.tracking
    image_width = float(clip.size[0])
    min_distance = int(image_width * 0.05)

    marker_adapt = markers_per_frame * 4
    detection_threshold = base_threshold
    count_new = 0
    step = 0
    while count_new < markers_per_frame:
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=16,
            threshold=detection_threshold,
            min_distance=min_distance,
        )
        new_tracks = [t for t in tracking.tracks if t.select]
        count_new = len(new_tracks)
        print(
            f"Detection step {step + 1}: threshold={detection_threshold}, "
            f"new_tracks={count_new}"
        )
        detection_threshold = max(
            min(
                detection_threshold * ((count_new + 0.1) / marker_adapt),
                1.0,
            ),
            0.0001,
        )
        step += 1
        if step > 10:
            break
    return count_new


def _frame_coverage_analysis(context, markers_per_frame, threshold, csv_path=None):
    """Analysiert Marker pro Frame, protokolliert Statistiken und füllt Lücken."""
    print(
        f"Frame coverage analysis: markers_per_frame={markers_per_frame}, "
        f"threshold={threshold}"
    )
    scene = context.scene
    clip = context.space_data.clip
    tracking_obj = clip.tracking.objects.active
    start = clip.frame_start
    end = start + clip.frame_duration
    counts = _marker_counts(tracking_obj, start, end)
    print(f"Marker count per frame: {counts}")
    if counts:
        min_count = min(counts.values())
        max_count = max(counts.values())
        median_count = statistics.median(counts.values())
        print(
            f"Coverage stats -> min:{min_count}, max:{max_count}, "
            f"median:{median_count}"
        )
    else:
        min_count = max_count = median_count = 0

    if csv_path:
        import csv
        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["frame", "count"])
            for frame, count in counts.items():
                writer.writerow([frame, count])

    needed = [f for f, c in counts.items() if c < markers_per_frame]
    print(f"Frames needing markers: {needed}")
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
    return counts, needed


def run_tracking(context, markers_per_frame, min_frames, error_limit, max_attempts=3):
    """Führt adaptives Tracking mit Wiederholungen durch."""
    print(
        "Run tracking: markers_per_frame="
        f"{markers_per_frame}, min_frames={min_frames}, "
        f"error_limit={error_limit}, max_attempts={max_attempts}"
    )
    clip = context.space_data.clip
    tracking = clip.tracking
    settings = tracking.settings
    image_width = float(clip.size[0])
    settings.default_pattern_size = max(int(image_width / 100), 5)
    settings.default_search_size = settings.default_pattern_size
    settings.default_motion_model = "Loc"
    settings.default_pattern_match = "KEYFRAME"
    settings.default_correlation_min = 0.9

    start = clip.frame_start
    end = start + clip.frame_duration

    threshold = 0.5
    for attempt in range(max_attempts):
        print(f"[Tracking Pass {attempt + 1}] Threshold={threshold}")
        bpy.ops.clip.select_all(action="DESELECT")
        _adaptive_detect(clip, markers_per_frame, threshold)

        detected = len(tracking.objects.active.tracks)
        error_limits = [error_limit, error_limit * 1.5, error_limit * 2.0, error_limit * 3.0]
        for limit in error_limits:
            clean_tracks(tracking.objects.active, min_frames, limit)
            counts = _marker_counts(tracking.objects.active, start, end)
            if counts and min(counts.values()) >= markers_per_frame:
                break

        valid_after = len(tracking.objects.active.tracks)
        avg_len = _average_track_length(tracking.objects.active)
        needed_frames = [f for f, c in counts.items() if c < markers_per_frame]

        print(f"→ Detected {detected} tracks")
        print(
            f"→ Valid after cleanup: {valid_after} "
            f"(min_frames={min_frames}, error_limit={limit})"
        )
        print(f"→ Avg. marker length: {avg_len:.1f} frames")
        if needed_frames:
            print(f"→ Frames with <{markers_per_frame} markers: {needed_frames}")

        if not needed_frames:
            print("Sufficient tracks detected")
            break

        threshold *= 1.5
        print(f"Not enough tracks, increasing threshold to {threshold}")

    counts, needed = _frame_coverage_analysis(context, markers_per_frame, threshold)
    context.scene.kaiserlich_marker_counts = counts
    print("Tracking run completed")


__all__ = ["run_tracking"]
