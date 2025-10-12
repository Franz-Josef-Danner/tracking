from __future__ import annotations
import bpy

def get_total_track_length(context: bpy.types.Context, start_frame: int) -> int:
    """Ermittelt die Gesamt-Länge aller Marker-Segmente ab einem Startframe."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[track_length_helper] ❌ Kein Clip im aktuellen Context.")
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("[track_length_helper] ❌ Clip hat kein Tracking-Objekt.")
        return 0

    # Verwende aktives Tracking-Objekt (nicht nur tracking.tracks)
    active_object = getattr(tracking, "objects", None)
    if active_object and getattr(tracking.objects, "active", None):
        tracks = tracking.objects.active.tracks
        print(f"[track_length_helper] Verwende active object: {tracking.objects.active.name}")
    else:
        tracks = tracking.tracks
        print("[track_length_helper] Verwende default tracking.tracks")

    print(f"[track_length_helper] Startframe: {start_frame}")
    print(f"[track_length_helper] Anzahl Tracks: {len(tracks)}")

    total_length = 0
    for i, tr in enumerate(tracks):
        print(f"[track_length_helper] → Track {i}: Name='{tr.name}', selected={tr.select}, markers={len(tr.markers)}")

        marker_frames = [mk.frame for mk in tr.markers if mk.frame >= start_frame]
        print(f"[track_length_helper]   Marker ab {start_frame}: {marker_frames}")

        if not marker_frames:
            continue

        min_frame = min(marker_frames)
        max_frame = max(marker_frames)
        length = max_frame - min_frame + 1
        print(f"[track_length_helper]   Länge Segment = {length} (von {min_frame} bis {max_frame})")

        total_length += length

    print(f"[track_length_helper] ✅ Gesamt-Track-Länge = {total_length}")
    return total_length
