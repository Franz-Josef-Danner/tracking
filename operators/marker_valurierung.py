import bpy

from ..helpers import (
    test_marker_base,
    place_marker_operator,
    track_markers_until_end,
    error_value,
    get_tracking_lengths,
    cycle_motion_model,
    set_tracking_channels,
)


class CLIP_OT_marker_valurierung(bpy.types.Operator):
    bl_idname = "clip.marker_valurierung"
    bl_label = "Marker Valurierung"
    bl_description = (
        "Pr\u00fcft die Markeranzahl pro Frame und startet bei Bedarf einen Tracking-Zyklus"
    )

    _repeat: int = 0

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        threshold = test_marker_base(scene)

        for frame in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_current = frame
            count = sum(
                1
                for t in clip.tracking.tracks
                if not t.hide
                and (m := t.markers.find_frame(frame))
                and not m.mute
                and m.co.length_squared != 0.0
            )
            if count < threshold:
                self._repeat += 1
                if self._repeat >= 10:
                    cycle_motion_model(clip.tracking.settings, clip, reset_size=False)
                    set_tracking_channels(clip.tracking.settings, True, True, True)
                    place_marker_operator(frame)
                    track_markers_until_end(scene)
                    err = error_value(clip)
                    lengths = get_tracking_lengths(clip)
                    print(
                        f"[Marker Valurierung] L\u00e4ngen={lengths} Error={err:.4f}"
                    )
                    self._repeat = 0
            else:
                self._repeat = 0
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_marker_valurierung,
)
