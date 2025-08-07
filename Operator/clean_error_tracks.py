# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.mute_invalid_segments import (
    remove_segment_boundary_keys,
    prune_outside_segments,
)


def _tracks_with_gaps(tracks):
    """Tracks finden, die innere Lücken haben (mehr als ein Segment)."""
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
    """Selektierte Tracks duplizieren & einfügen (UI-sicher)."""
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.copy_tracks()
        bpy.ops.clip.paste_tracks()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=5)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.15)


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (4-pass alt mute/delete)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, action="mute"):
        scene = context.scene
        clip = space.clip
        tracks = clip.tracking.tracks

        # 1) Tracks mit Lücken duplizieren und „splitten“ (vorne/hinten behalten)
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

        # 2) Keys GENAU auf Segmentgrenzen entfernen (nur wenn wirklich "keyed")
        remove_segment_boundary_keys(list(tracks), only_if_keyed=True)

        # 3) Alles außerhalb zusammenhängender Segmente (>=2 Frames) muten/löschen
        prune_outside_segments(list(tracks), action=action)

        bpy.context.view_layer.update()

    def execute(self, context):
        # Clip-Editor-Kontext ermitteln
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

        # Vier Durchläufe im Wechsel
        actions = ("mute", "delete", "mute", "delete")
        for i, action in enumerate(actions, start=1):
            print(f"[Cleanup] Pass {i}/4 – {action}")
            self._one_pass(context, clip_area, clip_region, clip_space, action=action)

        self.report({'INFO'}, "Cleanup fertig (4 Pässe, mute/delete im Wechsel).")
        return {'FINISHED'}
