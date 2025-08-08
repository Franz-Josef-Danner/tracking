# Helper/clear_path_on_split_tracks_segmented.py
import bpy
import time
from .process_marker_path import get_track_segments

def _select_only(space, track):
    tracks = space.clip.tracking.tracks
    for t in tracks:
        t.select = False
    track.select = True

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Schneidet Track-Pfade mit Blender-Operator:
      - ORIGINAL: behält vorderes Segment -> alles NACH dessen Ende löschen (REMAINED)
      - NEU:      behält hinteres Segment -> alles VOR dessen Anfang löschen (UPTO)
    """
    if not space or not space.clip:
        return

    with context.temp_override(area=area, region=region, space_data=space):
        # ORIGINAL-TRACKS: nur erstes (vorderstes) Segment behalten
        for tr in original_tracks:
            segs = get_track_segments(tr)
            if not segs:
                continue
            keep_end = segs[0][1]  # Ende des ersten Segments
            # nur diesen Track selektieren
            _select_only(space, tr)
            # auf Segment-Endframe springen
            context.scene.frame_set(keep_end)
            # alles danach löschen
            bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=True)

        # NEW-TRACKS: nur letztes (hinterstes) Segment behalten
        for tr in new_tracks:
            segs = get_track_segments(tr)
            if not segs:
                continue
            keep_start = segs[-1][0]  # Anfang des letzten Segments
            _select_only(space, tr)
            context.scene.frame_set(keep_start)
            # alles davor löschen
            bpy.ops.clip.clear_track_path(action='UPTO', clear_active=True)

        # sanfte UI-Aktualisierung
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
        bpy.context.view_layer.update()
        time.sleep(0.03)
