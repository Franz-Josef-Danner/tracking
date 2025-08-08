# Operator/clean_short_tracks.py
import bpy
from ..Helper.process_marker_path import get_track_segments

class CLIP_OT_clean_short_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_short_tracks"
    bl_label = "Clean Short Tracks (safe)"
    bl_options = {'REGISTER', 'UNDO'}

    frames: bpy.props.IntProperty(name="Min Frames", default=25, min=1)
    action: bpy.props.EnumProperty(
        name="Action",
        items=[
            ('DELETE_SEGMENTS', "Delete Segments", "Delete only short segments"),
            ('DELETE_TRACK',    "Delete Track",    "Delete the whole track if its longest segment is short"),
        ],
        default='DELETE_SEGMENTS'
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        # Clip-Editor-Kontext für Operator-Aufrufe sichern
        area = region = space = None
        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area, region, space = a, r, a.spaces.active
                        break

        clip = space.clip
        tracks = list(clip.tracking.tracks)

        removed_tracks = 0
        removed_segments = 0

        def delete_segment_markers(track, start, end):
            for f in range(start, end + 1):
                if track.markers.find_frame(f):
                    track.markers.delete_frame(f)

        with context.temp_override(area=area, region=region, space_data=space):
            for t in tracks:
                if not getattr(t, "markers", None):
                    continue

                segs = get_track_segments(t)  # -> [(start, end), ...]
                if not segs:
                    continue

                lens = [(s, e, e - s + 1) for (s, e) in segs]
                longest = max(L for _, _, L in lens)

                if self.action == 'DELETE_TRACK':
                    # ganzer Track nur, wenn selbst das längste Segment < frames ist
                    if longest < self.frames:
                        t.select = True
                        bpy.ops.clip.delete_track()
                        removed_tracks += 1
                    else:
                        t.select = False
                else:  # DELETE_SEGMENTS
                    for s, e, L in lens:
                        if L < self.frames:
                            delete_segment_markers(t, s, e)
                            removed_segments += 1

        self.report(
            {'INFO'},
            f"Short-tracks cleanup: removed_tracks={removed_tracks}, removed_segments={removed_segments}"
        )
        return {'FINISHED'}
