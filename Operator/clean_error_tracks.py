# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.process_marker_path import get_track_segments, process_marker_path
from ..Helper.mute_invalid_segments import mute_invalid_segments  # + remove_segment_boundary_keys falls du es benutzt
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, action: str):
        """Ein Cleanup-Pass mit bestimmter Aktion ('mute' | 'delete')."""
        scene = context.scene
        clip = space.clip
        tracks = clip.tracking.tracks

        # 1) Fehlerbereinigung (Grid)
        clean_error_tracks(context, space)

        # 2) Tracks mit internen Gaps duplizieren & Splitting-Mute
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if original_tracks:
            existing = {t.name for t in tracks}
            for t in tracks: t.select = False
            for t in original_tracks: t.select = True

            with context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.copy_tracks()
                bpy.ops.clip.paste_tracks()
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=5)
                scene.frame_set(scene.frame_current)
                bpy.context.view_layer.update()
                time.sleep(0.2)

            all_after = {t.name for t in tracks}
            new_names = all_after - existing
            new_tracks = [t for t in tracks if t.name in new_names]

            clear_path_on_split_tracks_segmented(
                context, area, region, space, original_tracks, new_tracks
            )  # mutet vor/nach Segmenten. :contentReference[oaicite:2]{index=2}

        # 3) harte Kanten säubern (Segment- und Trackgrenzen; nur echte Keys)
        remove_segment_boundary_keys(list(tracks), only_if_keyed=True, also_track_bounds=True)  # :contentReference[oaicite:3]{index=3}

        # 4) ungültige Marker behandeln (außerhalb gültiger Segmente / nach letztem Key)
        mute_invalid_segments(list(tracks), scene.frame_end, action=action)  # 'mute' oder 'delete' :contentReference[oaicite:4]{index=4}

        # Optional: superkurze Tracks wegputzen
        with context.temp_override(area=area, region=region, space_data=space):
            try:
                bpy.ops.clip.clean_short_tracks('INVOKE_DEFAULT')
            except Exception:
                pass

        # leichte UI-Refresh-Pause
        bpy.context.view_layer.update()
        time.sleep(0.05)

    def execute(self, context):
        # CLIP_EDITOR-Context besorgen
        area = region = space = None
        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area, region, space = a, r, a.spaces.active
        if not space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # Vier Durchläufe: mute → delete → mute → delete
        pass_plan = ["mute", "delete", "mute", "delete"]
        for i, action in enumerate(pass_plan, 1):
            print(f"[Cleanup] Pass {i}/4 – action={action}")
            self._one_pass(context, area, region, space, action=action)

        return {'FINISHED'}
