import bpy
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
    clip.use_proxy = False
    tracking = clip.tracking
    image_width = float(clip.size[0])
    min_distance = int(image_width * 0.05)

    marker_adapt = markers_per_frame * 4
    detection_threshold = base_threshold
    count_new = 0
    step = 0
    last_used_threshold = base_threshold
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
        last_used_threshold = detection_threshold
        detection_threshold = max(
            min(
                detection_threshold * ((count_new + 0.1) / marker_adapt), 1.0
            ),
            0.0001
        )
        # Formel gemäß Vorgabe aus "Kaiserlich Tracking Blender Operator.xlsx" – detect features_Formatiert_api_
        step += 1
        if step > 10:
            break
    if count_new < markers_per_frame:
        print(
            "Warnung: Markerzahl unter Zielwert – versuche aggressivere Detektion mit niedrigem Threshold."
        )
        bpy.ops.clip.select_all(action="SELECT")
        bpy.ops.clip.delete_track()
        detection_threshold = 0.1  # Minimalwert erzwingen
        count_new, last_used_threshold = _adaptive_detect(
            clip, markers_per_frame, detection_threshold
        )
    return count_new, last_used_threshold


def _frame_coverage_analysis(context, markers_per_frame, threshold, csv_path=None):
    """Analysiert Marker pro Frame, protokolliert Statistiken und füllt Lücken."""
    print(
        f"Frame coverage analysis: markers_per_frame={markers_per_frame}, "
        f"threshold={threshold}"
    )
    scene = context.scene
    clip = context.space_data.clip
    clip.use_proxy = False
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


def run_tracking(
    context,
    markers_per_frame=10,
    min_track_length=10,
    base_threshold=0.5,
    max_attempts=3,
):
    """Führt den kompletten Tracking-Workflow aus."""
    clip = context.space_data.clip
    tracking = clip.tracking
    start = clip.frame_start
    end = start + clip.frame_duration

    counts = {}
    for attempt in range(max_attempts):
        clip.use_proxy = False
        tracking.reset()

        # Step 1: Adaptive Marker Detection
        new_tracks, last_threshold = _adaptive_detect(
            clip, markers_per_frame, base_threshold
        )
        context.scene["kaiserlich_last_threshold"] = last_threshold
        print(f"{new_tracks} neue Marker gesetzt.")

        # Step 2: Bidirektional Tracken
        bpy.ops.clip.track_markers(backwards=False, sequence=False)
        bpy.ops.clip.track_markers(backwards=True, sequence=False)

        # Step 3: Zu kurze Tracks löschen
        short_tracks = [
            t
            for t in tracking.tracks
            if len([m for m in t.markers if not m.mute]) < min_track_length
        ]
        for t in short_tracks:
            tracking.tracks.remove(t)
        print(f"{len(short_tracks)} kurze Tracks entfernt.")

        # Step 4: Cleanup basierend auf Bewegung
        clean_tracks(tracking.objects.active, min_track_length, 2.0)

        counts = _marker_counts(tracking, start, end)
        if counts and min(counts.values()) >= markers_per_frame:
            break

        print(
            f"Zu wenige Marker ({min(counts.values()) if counts else 0}) – Wiederhole Versuch {attempt + 1}"
        )
    else:
        print("Trackingziel nicht erreicht")

    context.scene.kaiserlich_marker_counts = counts
    return counts


__all__ = ["run_tracking"]
