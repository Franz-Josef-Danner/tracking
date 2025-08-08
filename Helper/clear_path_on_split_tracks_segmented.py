import bpy
import time
from .process_marker_path import get_track_segments, process_marker_path

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Original-Tracks: vorderes Segment behalten -> danach muten
    New-Tracks: hinteres Segment behalten -> davor muten
    """
    with context.temp_override(area=area, region=region, space_data=space):
        # Originale: alles NACH Segment-Ende muten
        for track in original_tracks:
            segs = get_track_segments(track)
            for m in track.markers:
                m.mute = False
            for s, e in segs:
                process_marker_path(track, e + 1, 'forward', action='mute', mute=True)

        # Kopien: alles VOR Segment-Start muten
        for track in new_tracks:
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            bpy.context.view_layer.update()
            time.sleep(0.01)

            segs = get_track_segments(track)
            for m in track.markers:
                m.mute = False
            for s, e in segs:
                process_marker_path(track, s - 1, 'backward', action='mute', mute=True)
