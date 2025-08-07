from .process_marker_path import get_track_segments

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    with context.temp_override(area=area, region=region, space_data=space):
        for track in original_tracks:
            segments = get_track_segments(track)
            for m in track.markers:
                m.mute = False
            for seg in segments:
                process_marker_path(track, seg[-1] + 1, 'forward', action="mute", mute=True)

        for track in new_tracks:
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            bpy.context.view_layer.update()
            time.sleep(0.05)

            segments = get_track_segments(track)
            for m in track.markers:
                m.mute = False
            for seg in segments:
                process_marker_path(track, seg[0] - 1, 'backward', action="mute", mute=True)
