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
    Ermittelt die Gesamtanzahl aller aktiven Marker über alle Tracks.
    Jeder Frame, an dem ein Marker existiert, zählt als 1.
    Segmente werden ignoriert, es wird rein die Anzahl aktiver Marker summiert.
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

    # aktives Tracking-Objekt
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

    # === Hauptlogik: Aktive Marker zählen ===
    for tr in tracks:
        # Nur Marker ab Start-Frame zählen
        marker_frames = [mk.frame for mk in tr.markers if mk.frame >= start_frame]
        if not marker_frames:
            if log:
                print(f"{log_prefix} Track '{tr.name}': keine Marker ≥ {start_frame} → skip")
            continue

        count_active = len(marker_frames)
        total_length += count_active
        tracked_tracks += 1

        if log:
            print(f"{log_prefix} Track '{tr.name}': {count_active} aktive Marker gezählt")

    if log:
        print(f"{log_prefix} Ausgewertete Tracks: {tracked_tracks}")
        print(f"{log_prefix} Gesamtanzahl aktiver Marker (ab Frame {start_frame}): {total_length}")

    return total_length
