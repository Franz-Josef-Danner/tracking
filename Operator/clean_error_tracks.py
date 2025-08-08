# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.grid_error_cleanup import grid_error_cleanup
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented

# … (_count_all_markers, _tracks_with_gaps, _duplicate_selected_tracks) bleiben wie bei dir …

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid + optional Split)"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: bpy.props.BoolProperty(
        name="Verbose log",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, *, do_split=False):
        clip   = space.clip
        tracks = clip.tracking.tracks

        before_total = sum(len(getattr(t, "markers", [])) for t in tracks)

        # 1) Grid-Error-Cleanup (einmal)
        grid_deleted = 0
        try:
            grid_deleted = grid_error_cleanup(context, space, verbose=self.verbose)
        except Exception as e:
            if self.verbose:
                print(f"[GridError] übersprungen: {e}")

        # 2) Optional (nur im 1. Pass) Split der Gaps
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

                clear_path_on_split_tracks_segmented(
                    context, area, region, space,
                    original_tracks, new_tracks
                )

        bpy.context.view_layer.update()
        after_total = sum(len(getattr(t, "markers", [])) for t in tracks)

        changed = int(grid_deleted)
        if self.verbose:
            print(f"[Cleanup] grid_deleted={grid_deleted}, "
                  f"markers_before={before_total}, markers_after={after_total}, changed={changed}")
        return changed

    def execute(self, context):
        # Clip-Editor-Kontext suchen (sonst poll fail)
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

        # 👉 genau 1 Pass: Grid-Cleanup + optional Split
        changed = self._one_pass(
            context,
            clip_area, clip_region, clip_space,
            do_split=True
        )

        if self.verbose:
            print(f"[Cleanup] single pass finished, changed={changed}")

        self.report({'INFO'}, f"Cleanup beendet. Änderungen: {changed}")
        return {'FINISHED'}
