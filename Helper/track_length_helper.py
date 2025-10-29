from __future__ import annotations
import bpy
from typing import List, Tuple

def _segments_from_frames(frames: List[int]) -> List[Tuple[int, int, int]]:
    """
    Wandelt eine sortierte Frameliste in Segmente um.
    Rückgabe: Liste aus (seg_start, seg_end, seg_len).
    """
    if not frames:
        return []
    segs: List[Tuple[int, int, int]] = []
    seg_start = frames[0]
    prev = frames[0]
    for f in frames[1:]:
        if f - prev > 1:
            segs.append((seg_start, prev, prev - seg_start + 1))
            seg_start = f
        prev = f
    # letztes Segment
    segs.append((seg_start, prev, prev - seg_start + 1))
    return segs


def get_total_track_length(
    context: bpy.types.Context,
    start_frame: int = 1,
    *,
    log: bool = True,
    log_prefix: str = "[Kaiserlich Tracker][TrackLen]"
) -> int:
    """
    Ermittelt die Gesamt-Trackinglänge über alle Tracks (segmentbasiert).
    Optional mit ausführlichem Log pro Track und Gesamtsumme.
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

    # === Hauptlogik: Segmentbasierte Längenberechnung inkl. Logs ===
    for tr in tracks:
        # Marker ab Start-Frame
        marker_frames = sorted([mk.frame for mk in tr.markers if mk.frame >= start_frame])
        if not marker_frames:
            if log:
                print(f"{log_prefix} Track '{tr.name}': keine Marker ≥ {start_frame} → skip")
            continue

        segs = _segments_from_frames(marker_frames)
        seg_sum = sum(seg_len for _, _, seg_len in segs)
        total_length += seg_sum
        tracked_tracks += 1

        if log:
            # Segmente kompakt loggen: "a-b(len)"
            seg_str = ", ".join([f"{a}-{b}({l})" for (a, b, l) in segs])
            print(
                f"{log_prefix} Track '{tr.name}': Segmente=[{seg_str}] | Sum={seg_sum}"
            )

    if log:
        print(f"{log_prefix} Ausgewertete Tracks: {tracked_tracks}")
        print(f"{log_prefix} Gesamt-Länge (ab Frame {start_frame}): {total_length}")

    return total_length
