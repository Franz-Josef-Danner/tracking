from __future__ import annotations
import bpy

def get_total_track_length(context: bpy.types.Context, start_frame: int) -> int:
    """Return the sum of tracked segment lengths for all selected tracks."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print(f"[track_length_helper] Kein Clip gefunden (space_data.clip ist None).")
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print(f"[track_length_helper] Kein tracking-Attribut im Clip vorhanden.")
        return 0

    total_length = 0
    print(f"[track_length_helper] Startframe: {start_frame}")
    print(f"[track_length_helper] Anzahl Tracks insgesamt: {len(tracking.tracks)}")

    # Iteriere über alle Tracks, die ausgewählt sind
    for i, tr in enumerate(tracking.tracks):
        if not getattr(tr, "select", False):
            # Optional: Log nicht gewählter Tracks
            # print(f"[track_length_helper] Track {i}: nicht selektiert, überspringe.")
            continue

        # Alle Markerframes ab Startframe sammeln
        marker_frames = [mk.frame for mk in tr.markers if mk.frame >= start_frame]
        print(f"[track_length_helper] Track {i} (Name: {tr.name}): Marker-Frames ≥ {start_frame}: {marker_frames}")

        if not marker_frames:
            print(f"[track_length_helper] Track {i} hat keine Marker am oder nach Frame {start_frame}, übersprungen.")
            continue

        max_frame = max(marker_frames)
        length = (max_frame - start_frame + 1)
        print(f"[track_length_helper] Track {i}: max_frame = {max_frame}, Länge = {length}")

        total_length += length

    print(f"[track_length_helper] Gesamt-Track-Länge: {total_length}")
    return total_length
