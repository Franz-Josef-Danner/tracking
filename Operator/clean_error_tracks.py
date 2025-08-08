# Operator/clean_error_tracks.py
import bpy, time
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.mute_invalid_segments import remove_segment_boundary_keys, prune_outside_segments
from ..Helper.grid_error_cleanup import grid_error_cleanup

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
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.1)

def _count_all_markers(tracks):
    total = 0
    for t in tracks:
        try:
            total += len(t.markers)
        except Exception:
            pass
    return total

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname  = "clip.clean_error_tracks"
    bl_label   = "Clean Error Tracks (Grid + 4-pass mute/delete)"
    bl_options = {'REGISTER', 'UNDO'}

    # optionaler Schalter, falls du Logs mal leiser willst
    verbose: bpy.props.BoolProperty(name="Verbose cleanup log", default=True)

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, *, action="mute"):
        scene  = context.scene
        clip   = space.clip
        tracks = clip.tracking.tracks

        before_total = _count_all_markers(tracks)

        # 1) Lücken-tracks duplizieren & splitten
        original_tracks = _tracks_with_gaps(tracks)
        if original_tracks:
            existing_names = {t.name for t in tracks}
            for t in tracks: t.select = False
            for t in original_tracks: t.select = True

            _duplicate_selected_tracks(context, area, region, space)

            all_names = {t.name for t in tracks}
            new_names = all_names - existing_names
            new_tracks = [t for t in tracks if t.name in new_names]

            clear_path_on_split_tracks_segmented(
                context, area, region, space,
                original_tracks, new_tracks
            )

        # 2) Keyframes EXAKT am Segmentende killen (gegen "estimated" dahinter)
        removed_keys = remove_segment_boundary_keys(tracks, delete_start=False, delete_end=True)

        # 3) Alles außerhalb der Segmente entfernen/markieren, mit Guard
        muted, deleted = prune_outside_segments(tracks, guard_before=1, guard_after=1, action=action)

        bpy.context.view_layer.update()
        after_total = _count_all_markers(tracks)

        if self.verbose:
            print(
                f"[Cleanup] pass action={action}: "
                f"removed_boundary_keys={removed_keys}, muted={muted}, deleted={deleted}, "
                f"markers_before={before_total}, markers_after={after_total}"
            )

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

        # *** WICHTIG: 3-Frame Grid-Error-Cleanup zuerst ***
        grid_deleted = grid_error_cleanup(context, clip_space, verbose=True)
        if self.verbose:
            print(f"[GridError] deleted_markers_total={grid_deleted}")

        # Danach: 4 Pässe mute → delete → mute → delete
        for i, action in enumerate(("mute", "delete", "mute", "delete"), start=1):
            if self.verbose:
                print(f"[Cleanup] Pass {i}/4 – {action}")
            self._one_pass(context, clip_area, clip_region, clip_space, action=action)

        self.report({'INFO'}, "Cleanup fertig (Grid-Error + 4 Pässe).")
        return {'FINISHED'}
