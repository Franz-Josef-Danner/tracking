from typing import List, Dict, Any, Tuple
import bpy
from .delete import delete_track_by_name

MarkerSnapshot = Dict[str, Any]

def cleanup_new_markers(
    context,
    alte_marker: List[MarkerSnapshot],
    neue_marker: List[MarkerSnapshot],
    *,
    pz: int,
    hz: int,
    vc: int
) -> Tuple[List[MarkerSnapshot], int]:

    if not neue_marker or not alte_marker:
        return neue_marker, 0

    if pz <= 0:
        return neue_marker, 0

    # Tracking referenzieren für Aktiv-Filter
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    tracking = getattr(clip, "tracking", None) if clip else None

    def _track_active(name: str) -> bool:
        if not tracking:
            return False
        tr = tracking.tracks.get(name)
        return bool(tr and not getattr(tr, "mute", False))

    active_old = [m for m in alte_marker if _track_active(m["track"])]
    active_new = [m for m in neue_marker if _track_active(m["track"])]

    if not active_new or not active_old:
        return neue_marker, 0

    deleted_old = 0
    remaining_old = {(m["track"], m["frame"]): m for m in active_old}

    def build_old_pixel_map():
        # Normierte Koordinaten -> Pixel
        return [
            (key, m["co"][0] * hz, m["co"][1] * vc, m)
            for key, m in remaining_old.items()
        ]

    old_pixels = build_old_pixel_map()
    thresh = float(pz) * 0.025

    for nm in active_new:
        nm_px_x = float(nm["co"][0]) * hz
        nm_px_y = float(nm["co"][1]) * vc

        for key, ama_px_x, ama_px_y, ama_m in list(old_pixels):
            dx = abs(ama_px_x - nm_px_x)
            if dx < thresh:
                if delete_track_by_name(context, ama_m["track"]):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    old_pixels = build_old_pixel_map()
                continue

            dy = abs(ama_px_y - nm_px_y)
            if dy < thresh:
                if delete_track_by_name(context, ama_m["track"]):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    old_pixels = build_old_pixel_map()
                continue

    return neue_marker, deleted_old
