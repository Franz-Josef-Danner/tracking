from __future__ import annotations
import bpy


def get_total_track_length(context: bpy.types.Context, start_frame: int = 1) -> int:
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    # aktives Tracking-Objekt
    if getattr(tracking.objects, "active", None):
        tracks = tracking.objects.active.tracks
    else:
        tracks = tracking.tracks

    total_length = 0

    # === Hauptlogik: Segmentbasierte Längenberechnung ===
    for i, tr in enumerate(tracks):
        marker_frames = sorted([mk.frame for mk in tr.markers if mk.frame >= start_frame])
        if not marker_frames:
            continue

        seg_lengths = []
        seg_start = marker_frames[0]
        prev_frame = marker_frames[0]

        for frame in marker_frames[1:]:
            # Prüfe, ob eine Lücke >1 Frame besteht
            if frame - prev_frame > 1:
                seg_length = prev_frame - seg_start + 1
                seg_lengths.append(seg_length)
                seg_start = frame  # neues Segment beginnt
            prev_frame = frame

        # letztes Segment abschließen
        seg_lengths.append(prev_frame - seg_start + 1)

        track_total = sum(seg_lengths)
        total_length += track_total
    return total_length
