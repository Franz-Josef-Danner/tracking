import bpy

from ..helpers.test_marker_base import test_marker_base
from .place_marker_operator import TRACKING_OT_place_marker
from ..helpers.track_markers_until_end import track_markers_until_end
from .error_value_operator import CLIP_OT_error_value
from ..helpers.get_tracking_lengths import get_tracking_lengths
from ..helpers.cycle_motion_model import cycle_motion_model
from ..helpers.set_tracking_channels import set_tracking_channels
from ..helpers.test_cyclus import run_tracking_optimization


class CLIP_OT_marker_valurierung(bpy.types.Operator):
    """Validiert die Markeranzahl pro Frame."""

    bl_idname = "clip.marker_valurierung"
    bl_label = "Marker Valurierung"
    bl_description = "\u00dcberpr\u00fcft die Markeranzahl pro Frame und startet bei Bedarf den Tracking-Zyklus"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"WARNING"}, "Kein Clip geladen")
            return {"CANCELLED"}

        values = test_marker_base(context)
        min_marker = int(values.get("min_marker", 0))

        repeat = 0
        start = scene.frame_start
        end = scene.frame_end

        for frame in range(start, end + 1):
            scene.frame_set(frame)
            count = 0
            for track in clip.tracking.tracks:
                marker = track.markers.find_frame(frame, exact=True)
                if marker and not marker.mute:
                    count += 1

            if count < min_marker:
                repeat += 1
            else:
                repeat = 0

            if repeat >= 10:
                self.report({"INFO"}, "Starte Tracking-Zyklus")
                run_tracking_optimization(context)
                repeat = 0

        self.report({"INFO"}, "Marker Valuierung abgeschlossen")
        return {"FINISHED"}
