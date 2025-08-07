# Helper/clear_path_on_split_tracks_segmented.py
import bpy
import time
from .process_marker_path import get_track_segments, process_marker_path


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Original-Tracks: vorderes Segment behalten → alles danach muten
    New-Tracks: hinteres Segment behalten → alles davor muten
    """
    with context.temp_override(area=area, region=region, space_data=space):
        # ORIGINAL
        for track in original_tracks:
            for m in track.markers:
                m.mute = False
            for start, end in get_track_segments(track):
                process_marker_path(track, end + 1, "forward", action="mute", mute=True)

        # NEW
        for track in new_tracks:
            # UI-Refresh für sicheres Auffinden der Marker
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            bpy.context.view_layer.update()
            time.sleep(0.05)

            for m in track.markers:
                m.mute = False
            for start, end in get_track_segments(track):
                process_marker_path(track, start - 1, "backward", action="mute", mute=True)
