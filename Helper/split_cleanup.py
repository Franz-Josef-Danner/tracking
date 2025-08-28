# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
import bpy
from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers, mute_after_last_marker
from .clean_short_tracks import clean_short_tracks

# Scene-Schalter: wenn True, werden ausführliche Logs ausgegeben.
_VERBOSE_SCENE_KEY = "tco_verbose_split"


def _is_verbose(scene) -> bool:
    try:
        return bool(scene.get(_VERBOSE_SCENE_KEY, False))
    except Exception:
        return False


def _log(scene, msg: str) -> None:
    if _is_verbose(scene):
        print(f"[SplitCleanup] {msg}")


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """Behalte beim Original den vorderen, beim Duplikat den hinteren Segmentanteil (per Muting)."""
    scene = context.scene
    clip = space.clip
    _log(scene, "clear_path_on_split_tracks_segmented: start")

    # Rebinding per Name (robust gegenüber Copy/Paste)
    tracks_by_name = {}
    for t in clip.tracking.tracks:
        tn = _safe_name(t)
        if tn:
            tracks_by_name[tn] = t

    _log(scene, f"rebind: have {len(tracks_by_name)} tracks in clip")

    original_tracks = [tracks_by_name[_safe_name(n)]
                       for n in original_tracks
                       if _safe_name(n) in tracks_by_name]
    new_tracks = [tracks_by_name[_safe_name(n)]
                  for n in new_tracks
                  if _safe_name(n) in tracks_by_name]

    _log(scene, f"rebind result: originals={len(original_tracks)} new={len(new_tracks)}")

    redraw_budget = 0
    with context.temp_override(area=area, region=region, space_data=space):
        # Original: vorderes Segment behalten → danach muten
        for track in original_tracks:
            segs = list(get_track_segments(track))
            _log(scene, f"original '{track.name}': segments={len(segs)}")
            for seg in segs:
                # seg ist [f_start, ..., f_end]; alles NACH dem Segment muten
                mute_marker_path(track, seg[-1] + 1, 'forward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()

        # Neu: hinteres Segment behalten → davor muten
        for track in new_tracks:
            segs = list(get_track_segments(track))
            _log(scene, f"new '{track.name}': segments={len(segs)}")
            for seg in segs:
                # alles VOR dem Segment muten
                mute_marker_path(track, seg[0] - 1, 'backward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()

        # Harte Sync
        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        region.tag_redraw()

    _log(scene, "clear_path_on_split_tracks_segmented: done")


def recursive_split_cleanup(context, area, region, space, tracks):
    """Zerlegt Tracks mit internen Lücken iterativ in saubere Segmente; finaler Clean- und Safety-Pass."""
    scene = context.scene
    iteration = 0
    previous_gap_count = -1
    MAX_ITERATIONS = 5

    _log(scene, "recursive_split_cleanup: start")

    if "processed_tracks" not in scene:
        scene["processed_tracks"] = []

    while iteration < MAX_ITERATIONS:
        iteration += 1
        processed = list(scene.get("processed_tracks", []))

        # Kandidaten: Tracks mit internen Gaps, die noch nicht bearbeitet wurden
        original_tracks = [
            t for t in tracks
            if track_has_internal_gaps(t) and t.name not in processed
        ]

        _log(scene, f"iter={iteration}: candidates={len(original_tracks)} processed={len(processed)}")

        if not original_tracks:
            _log(scene, "iter: no more tracks with internal gaps → break")
            break
        if previous_gap_count == len(original_tracks):
            _log(scene, "iter: no progress (gap count unchanged) → break")
            break

        previous_gap_count = len(original_tracks)

        # Auswahl vorbereiten (kopieren/duplizieren)
        existing_names = {t.name for t in tracks}
        for t in tracks:
            try:
                t.select = False
            except Exception:
                pass
        for t in original_tracks:
            try:
                t.select = True
            except Exception:
                pass

        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        # Neu erzeugte Duplikate identifizieren
        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]
        _log(scene, f"iter={iteration}: new_tracks={len(new_tracks)}")

        # processed aktualisieren
        for t in original_tracks + new_tracks:
            if t.name not in processed:
                processed.append(t.name)
        scene["processed_tracks"] = processed

        # Segmentseitiges Muting (vorne behalten / hinten behalten)
        clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks)

    # Abschluss im gültigen UI-Kontext
    with context.temp_override(area=area, region=region, space_data=space):
        _log(scene, "final: clean_short_tracks(action='DELETE_TRACK')")
        clean_short_tracks(context, action="DELETE_TRACK")

    # Safety-Pass
    _log(scene, "final: mute_unassigned_markers + FINISHED")
    mute_unassigned_markers(tracks)
    return {'FINISHED'}
