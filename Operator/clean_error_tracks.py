# Operator/clean_error_tracks.py
import bpy, time
from ..Helper.grid_error_cleanup import grid_error_cleanup
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.mute_invalid_segments import (
    remove_segment_boundary_keys,
    prune_outside_segments,
)


# --- Helpers (falls nicht vorhanden) -----------------------------------------

def _count_all_markers(tracks):
    return sum(len(getattr(t, "markers", [])) for t in tracks)

def _tracks_with_gaps(tracks):
    out = []
    for t in tracks:
        try:
            segs = get_track_segments(t)
        except Exception:
            segs = []
        if len(segs) >= 2:
            out.append(t)
    return out

def _duplicate_selected_tracks(context, area, region, space):
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.copy_tracks()
        bpy.ops.clip.paste_tracks()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=4)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.1)

# --- Operator: ersetze NUR diese beiden Methoden -----------------------------

def _one_pass(self, context, area, region, space, *, action="mute", do_split=False):
    """
    Ein Cleanup-Pass:
      1) Grid-Error-Cleanup (3-Frame-Ausreißer)
      2) Optional Splitten (nur im 1. Pass)
      3) Boundary-Keyframes am Segment-Ende löschen
      4) Bereiche außerhalb der (unmuteten) Segmente mit Guard entfernen/muten
    """
    scene  = context.scene
    clip   = space.clip
    tracks = clip.tracking.tracks

    before_total = _count_all_markers(tracks)

    # 1) 3-Frame-Error-Filter (Grid)
    try:
        # macht nur etwas, wenn Marker vorhanden sind; sonst no-op
        grid_error_cleanup(context, space)
    except Exception as e:
        if getattr(self, "verbose", False):
            print(f"[GridError] übersprungen: {e}")

    # 2) Nur im ersten Pass splitten/duplizieren
    if do_split:
        original_tracks = _tracks_with_gaps(tracks)
        if original_tracks:
            existing_names = {t.name for t in tracks}
            for t in tracks:
                t.select = False
            for t in original_tracks:
                t.select = True

            _duplicate_selected_tracks(context, area, region, space)

            all_names = {t.name for t in tracks}
            new_names = all_names - existing_names
            new_tracks = [t for t in tracks if t.name in new_names]

            # vorderes/hinteres Segment behalten, Rest muten
            clear_path_on_split_tracks_segmented(
                context, area, region, space,
                original_tracks, new_tracks
            )

    # 3) Keyframes EXAKT am Segmentende löschen (gegen "estimated" dahinter)
    removed_keys = 0
    try:
        removed_keys = remove_segment_boundary_keys(
            list(tracks), delete_start=False, delete_end=True
        )
    except Exception as e:
        if getattr(self, "verbose", False):
            print(f"[BoundaryKeys] übersprungen: {e}")

    # 4) Außerhalb der Segmente aufräumen (mit Guard)
    muted = deleted = 0
    try:
        muted, deleted = prune_outside_segments(
            list(tracks),
            guard_before=1, guard_after=1,
            action=action
        )
    except Exception as e:
        if getattr(self, "verbose", False):
            print(f"[PruneOutside] übersprungen: {e}")

    bpy.context.view_layer.update()
    after_total = _count_all_markers(tracks)

    if getattr(self, "verbose", False):
        print(
            f"[Cleanup] pass action={action}: "
            f"removed_boundary_keys={removed_keys}, muted={muted}, deleted={deleted}, "
            f"markers_before={before_total}, markers_after={after_total}"
        )

    # optional: Rückgabewerte für Tests/Logs
    return removed_keys, muted, deleted, before_total, after_total


def execute(self, context):
    # Clip-Editor-Kontext einsammeln
    clip_area = clip_region = clip_space = None
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    clip_area = area
                    clip_region = region
                    clip_space = area.spaces.active
                    break

    if not clip_space:
        self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
        return {'CANCELLED'}

    actions = ("mute", "delete", "mute", "delete")
    for i, act in enumerate(actions, start=1):
        if getattr(self, "verbose", False):
            print(f"[Cleanup] Pass {i}/4 – {act}")
        self._one_pass(
            context, clip_area, clip_region, clip_space,
            action=act,
            do_split=(i == 1)  # Split nur im ersten Durchlauf!
        )

    self.report({'INFO'}, "Cleanup fertig (4 Pässe: mute/delete im Wechsel).")
    return {'FINISHED'}

