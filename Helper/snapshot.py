import bpy
from typing import List, Dict, Any

# Datentyp für einen einfachen Marker-Snapshot
MarkerSnapshot = Dict[str, Any]

def snapshot_active_markers(context) -> List[MarkerSnapshot]:
    """Erfasst alle **aktiven** (Track nicht gemutet, Marker nicht gemutet)
    Marker im aktuellen Frame. Rückgabe:
    { 'track': str, 'frame': int, 'co': (x, y), 'is_keyed': bool }
    """
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip is None:
        return []

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return []

    current_frame = int(getattr(context.scene, "frame_current", 0))
    out: List[MarkerSnapshot] = []

    for track in tracking.tracks:
        # Nur **aktive** Tracks berücksichtigen
        if getattr(track, "mute", False):
            continue

        marker = track.markers.find_frame(current_frame)
        if marker is None:
            continue
        # Nur **aktive** Marker berücksichtigen
        if getattr(marker, "mute", False):
            continue

        out.append({
            "track": track.name,
            "frame": int(marker.frame),
            "co": (float(marker.co[0]), float(marker.co[1])),
            "is_keyed": bool(getattr(marker, "is_keyed", False)),
        })

    return out
