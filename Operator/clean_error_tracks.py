import bpy
from ..Helper.multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from ..Helper.prune_tracks_density import prune_tracks_density
from ..Helper.segments import track_has_internal_gaps
from ..Helper.mute_ops import mute_after_last_marker, mute_unassigned_markers
from ..Helper.split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip_editor_area = clip_editor_region = clip_editor_space = None

        # 1) CLIP_EDITOR-Kontext ermitteln
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        clip_editor_area = area
                        clip_editor_region = region
                        clip_editor_space = area.spaces.active
                        break

        if not clip_editor_space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # 2) Dichte-Pruning
        prune_res = prune_tracks_density(context, threshold_key="marker_frame", dry_run=False)
        if prune_res.get("status") != "ok":
            print(f"[PruneDensity] status={prune_res.get('status')}")
        else:
            print(f"[PruneDensity] frames_processed={prune_res.get('frames_processed')} "
                  f"deleted_tracks={prune_res.get('deleted_tracks')} "
                  f"threshold={prune_res.get('threshold')}")

        # Depsgraph/Layers sync im gültigen Kontext
        with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=clip_editor_space):
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        # 3) Multiscale-Grid-Clean
        clip = clip_editor_space.clip
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)
        deleted = multiscale_temporal_grid_clean(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            list(clip.tracking.tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=3,
            outlier_q=0.90, hysteresis_hits=2, min_cell_items=4
        )
        print(f"[MultiScale] total deleted: {deleted}")

        tracks = clip.tracking.tracks

        # 4) Gap-Erkennung & Aufteilung
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            self.report({'INFO'}, "Keine Tracks mit Lücken gefunden.")
            return {'FINISHED'}

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=clip_editor_space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        clear_path_on_split_tracks_segmented(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            original_tracks, new_tracks
        )

        # 5) Rekursiver Split/Cleanup bis keine Gaps mehr vorhanden
        recursive_split_cleanup(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            tracks
        )

        # 6) Safety Passes
        mute_unassigned_markers(tracks)
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)

        return {'FINISHED'}
