# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.mute_invalid_segments import remove_segment_boundary_keys


def _tracks_with_gaps(tracks):
    """Tracks mit internen Lücken (>=2 Segmente) finden."""
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
    """Selektierte Tracks duplizieren (Copy/Paste) und UI kurz aktualisieren."""
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.copy_tracks()
        bpy.ops.clip.paste_tracks()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=4)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.1)


def _prune_outside_segments(track_or_tracks, action="mute"):
    """
    Alles, was NICHT in einem Segment mit Länge >=2 liegt, wird gemutet/gelöscht.
    KEIN hartes Abschneiden nach letztem Keyframe (kein 'last_keyed'-Cut)!
    """
    def _iter(x):
        try:
            return list(x)
        except TypeError:
            return [x]

    for track in _iter(track_or_tracks):
        markers = getattr(track, "markers", None)
        if not markers:
            continue

        segs = get_track_segments(track)
        if not segs:
            # keine Segmente -> alles mute/delete
            if action == "delete":
                for m in list(markers):
                    markers.delete_frame(m.frame)
            else:
                for m in markers:
                    m.mute = True
            continue

        valid_frames = set()
        for s, e in segs:
            if e - s + 1 >= 2:
                valid_frames.update(range(s, e + 1))

        if action == "delete":
            to_delete = [m.frame for m in list(markers) if m.frame not in valid_frames]
            for f in sorted(set(to_delete)):
                markers.delete_frame(f)
        else:
            for m in markers:
                if m.frame not in valid_frames:
                    m.mute = True


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

        # 1) Tracks mit Lücken duplizieren und „splitten“
        original_tracks = _tracks_with_gaps(tracks)
        if original_tracks:
            existing_names = {t.name for t in tracks}
            for t in tracks:
                t.select = False
            for t in original_tracks:
                t.select = True

            _duplicate_selected_tracks(context, area, region, space)

            # neue Tracks ermitteln
            all_names = {t.name for t in tracks}
            new_names = all_names - existing_names
            new_tracks = [t for t in tracks if t.name in new_names]

            # pro Segment: bei Originals vorderes, bei Kopien hinteres Segment behalten
            clear_path_on_split_tracks_segmented(
                context, area, region, space,
                original_tracks, new_tracks
            )

        # 2) Keys GENAU auf Segment- & Trackgrenzen entfernen (harter Fix gegen "estimated danach")
        remove_segment_boundary_keys(list(tracks), only_if_keyed=True, also_track_bounds=True)

        # 3) Alles außerhalb gültiger Segmente stummschalten/entfernen (ohne last_keyed-Schnitt)
        _prune_outside_segments(list(tracks), action=action)

        bpy.context.view_layer.update()

    def execute(self, context):
        # Clip-Editor-Kontext finden
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

        # 4 Durchläufe: mute → delete → mute → delete
        actions = ("mute", "delete", "mute", "delete")
        for i, action in enumerate(actions, start=1):
            print(f"[Cleanup] Pass {i}/4 – {action}")
            self._one_pass(context, clip_area, clip_region, clip_space, action=action)

        self.report({'INFO'}, "Cleanup fertig (4 Pässe).")
        return {'FINISHED'}
