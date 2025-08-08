# Operator/clean_error_tracks.py
import bpy, time
from ..Helper.grid_error_cleanup import grid_error_cleanup
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented

# --- kleine Helfer -----------------------------------------------------------

def _count_all_markers(tracks):
    return sum(len(getattr(t, "markers", [])) for t in tracks)

def _tracks_with_gaps(tracks):
    """Tracks mit >= 2 Segmenten (interne Lücken)."""
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
    """Selektierte Tracks duplizieren, UI kurz aktualisieren."""
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.copy_tracks()
        bpy.ops.clip.paste_tracks()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.05)

# --- eigentlicher Operator ---------------------------------------------------

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid + optional Split)"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: bpy.props.BoolProperty(
        name="Verbose log",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, *, do_split=False):
        """
        Ein Cleanup-Pass:
          1) Grid-Error-Cleanup (3-Frame-Ausreißer → Tripel löschen)
          2) Optional (nur im 1. Pass): Lücken-Tracks duplizieren & splitten
        """
        clip   = space.clip
        tracks = clip.tracking.tracks

        before_total = _count_all_markers(tracks)

        # 1) Grid-Error-Cleanup
        grid_deleted = 0
        try:
            grid_deleted = grid_error_cleanup(context, space, verbose=False)
        except Exception as e:
            if self.verbose:
                print(f"[GridError] übersprungen: {e}")

        # 2) Nur im ersten Pass splitten
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
        after_total = _count_all_markers(tracks)

        changed = grid_deleted
        if self.verbose:
            print(f"[Cleanup] grid_deleted={grid_deleted}, "
                  f"markers_before={before_total}, markers_after={after_total}, changed={changed}")
        return changed

    def execute(self, context):
        # Clip-Editor-Kontext suchen
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

        total_changes = 0
        # 4 Durchläufe – Split nur im ersten
        for i in range(1, 5):
            changed = self._one_pass(
                context, clip_area, clip_region, clip_space,
                do_split=(i == 1)
            )
            total_changes += changed
            if i == 1 and changed == 0:
                if self.verbose:
                    print("[Cleanup] Keine Änderungen im 1. Pass – breche ab.")
                break

        self.report({'INFO'}, f"Cleanup beendet. Total changes: {total_changes}")
        return {'FINISHED'}
