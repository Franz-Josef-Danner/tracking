# Helper/clear_path_on_split_tracks_segmented.py

import time
import bpy
from .process_marker_path import get_track_segments


def _activate_only(clip, track):
    """Nur den gegebenen Track aktiv/selektiert setzen."""
    for t in clip.tracking.tracks:
        t.select = False
    clip.tracking.tracks.active = track
    track.select = True


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Split-Cleanup mit harten Lösch-Operationen:

    - ORIGINAL-TRACKS: vorderstes Segment behalten -> alles DANACH löschen
      (Frame = SegmentEnde, action='REMAINED')

    - NEW-TRACKS: hinterstes Segment behalten -> alles DAVOR löschen
      (Frame = SegmentStart, action='UPTO')
    """
    with context.temp_override(area=area, region=region, space_data=space):
        clip = space.clip

        # ------- Original-Tracks: nur das vorderste Segment behalten -------
        for t in original_tracks:
            segs = get_track_segments(t)
            if not segs:
                continue

            start0, end0 = segs[0]  # vorderstes Segment
            _activate_only(clip, t)

            # Am Ende des vordersten Segments alles "danach" löschen
            context.scene.frame_set(end0)
            try:
                bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=True)
            except Exception as e:
                print(f"[clear_split][orig] {t.name}: REMAINED failed: {e}")

            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            bpy.context.view_layer.update()
            time.sleep(0.01)

        # ------- Neue (duplizierte) Tracks: nur das hinterste Segment behalten -------
        for t in new_tracks:
            segs = get_track_segments(t)
            if not segs:
                continue

            startN, endN = segs[-1]  # hinterstes Segment
            _activate_only(clip, t)

            # Bis zum Start des hintersten Segments alles "davor" löschen
            context.scene.frame_set(startN)
            try:
                bpy.ops.clip.clear_track_path(action='UPTO', clear_active=True)
            except Exception as e:
                print(f"[clear_split][new]  {t.name}: UPTO failed: {e}")

            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            bpy.context.view_layer.update()
            time.sleep(0.01)
