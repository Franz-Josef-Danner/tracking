import bpy
import json
import statistics
from .cleanup import clean_tracks
from .error_value import compute_marker_error_std


def delete_selected_tracks(tracking):
    """Remove tracks that are currently selected using index-based deletion."""
    i = 0
    while i < len(tracking.tracks):
        track = tracking.tracks[i]
        if track.select:
            print(f"[DEBUG] Entferne Track '{track.name}' an Index {i}")
            try:
                tracking.tracks.remove(i)
            except Exception as e:
                print(
                    f"[ERROR] Fehler beim Entfernen von Track '{track.name}' (Index {i}): {e}"
                )
        else:
            print(f"[DEBUG] Überspringe Track '{track.name}' an Index {i}")
            i += 1


def delete_track_by_name(tracking, name):
    """Remove a track from ``tracking`` by its ``name`` if present using index-based removal."""
    idx = tracking.tracks.find(name)
    if idx != -1 and idx < len(tracking.tracks):
        print(f"[DEBUG] Entferne Track '{name}' an Index {idx}")
        tracking.tracks.remove(idx)


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


def _adaptive_detect(clip, markers_per_frame, base_threshold, report=None):
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
    min_marker = markers_per_frame
    max_marker = marker_adapt
    detection_threshold = base_threshold
    last_used_threshold = base_threshold
    count_new = 0
    max_iterations = 10
    for iteration in range(max_iterations):
        print(
            f"[DEBUG] Detection-Versuch {iteration+1}: "
            f"Threshold={detection_threshold:.4f}, "
            f"Markerziel={markers_per_frame}, Basiswert={marker_adapt}"
        )
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=16,
            threshold=detection_threshold,
            min_distance=min_distance,
        )
        new_tracks = [t for t in tracking.tracks if t.select]
        count_new = len(new_tracks)
        print(f"[DEBUG] Anzahl neu detektierter Marker: {count_new}")
        if report:
            report(
                {'INFO'},
                f"Iteration {iteration+1}: threshold={detection_threshold:.4f}, marker={count_new}",
            )
        last_used_threshold = detection_threshold

        if count_new > min_marker:
            if count_new < max_marker:
                break
            else:
                detection_threshold = max(
                    min(
                        detection_threshold * ((count_new + 0.1) / marker_adapt),
                        1.0,
                    ),
                    0.0001,
                )
                print(
                    f"[DEBUG] Angepasster Threshold: {detection_threshold:.4f} "
                    f"auf Basis von count_new={count_new}"
                )
                if report:
                    report(
                        {'INFO'},
                        f"Threshold angepasst auf: {detection_threshold:.4f}",
                    )
        else:
            detection_threshold = max(
                min(
                    detection_threshold * ((count_new + 0.1) / marker_adapt),
                    1.0,
                ),
                0.0001,
            )
            print(
                f"[DEBUG] Angepasster Threshold: {detection_threshold:.4f} "
                f"auf Basis von count_new={count_new}"
            )
            if report:
                report(
                    {'INFO'},
                    f"Threshold angepasst auf: {detection_threshold:.4f}",
                )
    else:
        if report:
            report(
                {'WARNING'},
                f"Abbruch nach {max_iterations} Versuchen – Markeranzahl unzureichend ({count_new})",
            )

    return count_new, last_used_threshold, "zyklus_1_fertig"


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
    scene["kaiserlich_marker_counts"] = json.dumps(counts)
    print(f"[DEBUG] Markerzählung gespeichert: {counts}")
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
    marker_adapt = markers_per_frame * 4
    for idx, f in enumerate(needed):
        scene.frame_current = f
        print(
            f"[DEBUG] Detection-Versuch {idx+1}: Threshold={threshold:.4f}, "
            f"Markerziel={markers_per_frame}, Basiswert={marker_adapt}"
        )
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=16,
            threshold=threshold,
            min_distance=min_distance,
        )
        new_tracks = [t for t in tracking_obj.tracks if t.select]
        count_new = len(new_tracks)
        print(f"[DEBUG] Anzahl neu detektierter Marker: {count_new}")
    return counts, needed


def run_tracking(
    context,
    markers_per_frame=10,
    min_track_length=10,
    base_threshold=0.5,
    max_attempts=3,
    bidirectional=True,
    report_func=None,
):
    """Führt den kompletten Tracking-Workflow aus."""
    clip = context.space_data.clip
    tracking = clip.tracking
    start = clip.frame_start
    end = start + clip.frame_duration

    counts = {}
    min_marker = markers_per_frame
    max_marker = markers_per_frame * 4
    for attempt in range(max_attempts):
        clip.use_proxy = False
        for t in tracking.tracks:
            t.select = True
        delete_selected_tracks(tracking)

        # Step 1: Adaptive Marker Detection
        new_tracks, last_threshold, status = _adaptive_detect(
            clip, markers_per_frame, base_threshold, report=report_func
        )
        # teil_cyclus_1_fertig
        context.scene["kaiserlich_last_threshold"] = last_threshold
        if report_func:
            report_func({'INFO'}, f"{new_tracks} neue Marker gesetzt")
        print(f"{new_tracks} neue Marker gesetzt.")

        if not (new_tracks > min_marker and new_tracks < max_marker):
            if report_func:
                report_func(
                    {'WARNING'},
                    f"Markeranzahl außerhalb des gültigen Bereichs ({new_tracks})",
                )
            continue

        # Step 2: Tracken
        bpy.ops.clip.track_markers(backwards=False, sequence=False)
        if bidirectional:
            print("[DEBUG] Starte bidirektionales Tracking")
            bpy.ops.clip.track_markers(backwards=True, sequence=False)
        if report_func:
            mode = "bidirektional" if bidirectional else "vorwärts"
            report_func({'INFO'}, f"Tracking {mode} ausgeführt")

        # Step 3: Zu kurze Tracks löschen
        short_tracks = [
            t
            for t in tracking.tracks
            if len([m for m in t.markers if not m.mute]) < min_track_length
        ]
        for t in tracking.tracks:
            t.select = False
        for t in short_tracks:
            t.select = True
        delete_selected_tracks(tracking)
        print(f"{len(short_tracks)} kurze Tracks entfernt.")

        # Step 4: Cleanup basierend auf Bewegung
        error_limit = 2.0
        print(f"[DEBUG] Starte Cleanup: min_frames={min_track_length}, error_limit={error_limit}")
        print(
            f"[DEBUG] Verbleibende Marker vor Cleanup: {len(tracking.tracks)}"
        )
        clean_tracks(tracking.objects.active, min_track_length, error_limit)
        if report_func:
            report_func({'INFO'}, "clean_tracks() aufgerufen")
        error_value = compute_marker_error_std(tracking)
        context.scene["kaiserlich_error_std"] = error_value
        if report_func:
            report_func(
                {'INFO'},
                f"Fehlerwert (STD-Summe): {error_value:.4f}",
            )

        counts = _marker_counts(tracking, start, end)
        context.scene["kaiserlich_marker_counts"] = json.dumps(counts)
        print(f"[DEBUG] Markerzählung gespeichert: {counts}")
        if counts is None or min(counts.values()) == 0:
            print("[WARN] Kein verwertbares Marker-Set gefunden – erneuter Versuch")
            continue
        if min(counts.values()) >= markers_per_frame:
            break

        print(
            f"Zu wenige Marker ({min(counts.values())}) – Wiederhole Versuch {attempt + 1}"
        )
    else:
        print("Trackingziel nicht erreicht")

    context.scene["kaiserlich_marker_counts"] = json.dumps(counts)
    print(f"[DEBUG] Markerzählung gespeichert: {counts}")
    final_tracks = list(tracking.tracks)
    print(f"[INFO] Tracking-Zyklus abgeschlossen mit {len(final_tracks)} finalen Tracks")
    return counts


__all__ = ["run_tracking"]
