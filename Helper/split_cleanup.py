# Helper/split_cleanup.py
import bpy
from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers, mute_after_last_marker

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    clip = space.clip
    # Rebinding per Name (robust ggü. Copy/Paste)
    tracks_by_name = {}
    for t in clip.tracking.tracks:
        tn = _safe_name(t)
        if tn:
            tracks_by_name[tn] = t

    original_tracks = [tracks_by_name[_safe_name(n)]
                       for n in original_tracks
                       if _safe_name(n) in tracks_by_name]
    new_tracks = [tracks_by_name[_safe_name(n)]
                  for n in new_tracks
                  if _safe_name(n) in tracks_by_name]

    redraw_budget = 0
    with context.temp_override(area=area, region=region, space_data=space):
        # Original: vorderes Segment behalten → danach muten
        for track in original_tracks:
            for seg in list(get_track_segments(track)):
                mute_marker_path(track, seg[-1] + 1, 'forward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()
        # Neu: hinteres Segment behalten → davor muten
        for track in new_tracks:
            for seg in list(get_track_segments(track)):
                mute_marker_path(track, seg[0] - 1, 'backward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()

        # Harte Sync
        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        region.tag_redraw()

def recursive_split_cleanup(context, area, region, space, tracks):
    scene = context.scene
    iteration = 0
    previous_gap_count = -1
    MAX_ITERATIONS = 5

    if "processed_tracks" not in scene:
        scene["processed_tracks"] = []

    while iteration < MAX_ITERATIONS:
        iteration += 1
        processed = list(scene.get("processed_tracks", []))

        original_tracks = [
            t for t in tracks
            if track_has_internal_gaps(t) and t.name not in processed
        ]
        if not original_tracks:
            break
        if previous_gap_count == len(original_tracks):
            break
        previous_gap_count = len(original_tracks)

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name]()_
