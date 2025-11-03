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
    """
    Bereinigt *neue* Marker, die zu nah an alten liegen.
    Alte Marker werden grundsätzlich nicht gelöscht.
    """

    if not neue_marker or not alte_marker:
        return neue_marker, 0
    if pz <= 0:
        return neue_marker, 0

    # Trackingreferenz
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

    deleted_new = 0
    protected_names = {m["track"] for m in active_old}

    def build_old_pixel_map():
        return [
            (m["co"][0] * hz, m["co"][1] * vc, m)
            for m in active_old
        ]

    old_pixels = build_old_pixel_map()
    thresh = float(pz) * 0.025

    for nm in list(active_new):
        nm_px_x = float(nm["co"][0]) * hz
        nm_px_y = float(nm["co"][1]) * vc

        too_close = False
        for ama_px_x, ama_px_y, ama_m in old_pixels:
            dx = abs(ama_px_x - nm_px_x)
            dy = abs(ama_px_y - nm_px_y)
            if dx < thresh and dy < thresh:
                print(
                    f"[Cleanup][DEL] Neuer Track '{nm['track']}' "
                    f"entfernt wegen Nähe zu altem '{ama_m['track']}' "
                    f"(dx={dx:.2f}, dy={dy:.2f})"
                )
                if delete_track_by_name(context, nm["track"]):
                    deleted_new += 1
                too_close = True
                break
        if too_close:
            continue

    return neue_marker, 0
