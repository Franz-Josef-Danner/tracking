import math
import bpy
from .delete_tracks import delete_selected_tracks
from .clean_pending_tracks import clean_pending_tracks
from .prefix_good import PREFIX_GOOD
from .prefix_track import PREFIX_TRACK
from .prefix_new import PREFIX_NEW


def remove_close_tracks(clip, new_tracks, distance_px, names_before):
    """Delete new tracks too close to existing ones."""
    frame = bpy.context.scene.frame_current
    width, height = clip.size
    valid_positions = []
    for gt in clip.tracking.tracks:
        if (
            gt.name.startswith(PREFIX_GOOD)
            or gt.name.startswith(PREFIX_TRACK)
            or gt.name.startswith(PREFIX_NEW)
        ):
            gm = gt.markers.find_frame(frame, exact=True)
            if gm and not gm.mute:
                valid_positions.append((gm.co[0] * width, gm.co[1] * height))

    close_tracks = []
    for nt in new_tracks:
        nm = nt.markers.find_frame(frame, exact=True)
        if nm and not nm.mute:
            nx = nm.co[0] * width
            ny = nm.co[1] * height
            for vx, vy in valid_positions:
                if math.hypot(nx - vx, ny - vy) < distance_px:
                    close_tracks.append(nt)
                    break

    for track in clip.tracking.tracks:
        track.select = False
    for t in close_tracks:
        t.select = True
    if close_tracks:
        if delete_selected_tracks():
            clean_pending_tracks(clip)

    names_after = {t.name for t in clip.tracking.tracks}
    return [t for t in clip.tracking.tracks if t.name in names_after - names_before]
