from __future__ import annotations
import bpy
from typing import List

def get_total_track_length(
    context: bpy.types.Context,
    start_frame: int = 1,
    *,
    log: bool = True,
    log_prefix: str = "[Kaiserlich Tracker][TrackLen]"
) -> int:
    """
    Zählt nur Frames mit *aktiven* Markern pro Track.
    Ein Marker gilt als aktiv, wenn:
      - marker.mute == False
      - marker.pattern_corners nicht leer oder Null ist
    Danach werden alle aktiven Frames pro Track summiert.
    """

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        if log:
            print(f"{log_prefix} Kein aktiver Clip im Kontext → Länge=0")
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        if log:
            print(f"{log_prefix} Kein Tracking-Container gefunden → Länge=0")
        return 0

    # aktives Tracking-Objekt verwenden
    if getattr(tracking.objects, "active", None):
        tracks = tracking.objects.active.tracks
        if log:
            print(f"{log_prefix} Nutze aktive Tracking-Objekt-Tracks (Count={len(tracks)})")
    else:
        tracks = tracking.tracks
        if log:
            print(f"{log_prefix} Nutze globale Tracks (Count={len(tracks)})")

    total_length = 0
    tracked_tracks = 0

    # === Hauptlogik: Nur aktive Marker zählen ===
    for tr in tracks:
        # aktive Marker nach Startframe
        active_frames = [
            mk.frame
            for mk in tr.markers
            if mk.frame >= start_frame
            and not getattr(mk, "mute", False)
            and any(corner != (0.0, 0.0) for corner in getattr(mk, "pattern_corners", []))
        ]

        if not active_frames:
            if log:
                print(f"{log_prefix} Track '{tr.name}': keine aktiven Marker ≥ {start_frame} → skip")
            continue

        count_active = len(active_frames)
        total_length += count_active
        tracked_tracks += 1

        if log:
            print(f"{log_prefix} Track '{tr.name}': {count_active} aktive Marker gezählt")

    if log:
        print(f"{log_prefix} Ausgewertete Tracks: {tracked_tracks}")
        print(f"{log_prefix} Gesamtanzahl aktiver Marker (ab Frame {start_frame}): {total_length}")

    return total_length
