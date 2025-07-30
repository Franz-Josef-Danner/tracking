import bpy

from ..helpers.low_marker_frame import low_marker_frame
from ..helpers.test_cyclus import test_cyclus


class CLIP_OT_low_marker_frame(bpy.types.Operator):
    """Sucht und verarbeitet Frames mit zu wenigen Markern"""

    bl_idname = "clip.low_marker_frame"
    bl_label = "Low Marker Frame"
    bl_description = "Suche und bearbeite Frames mit zu wenigen Markern"

    repeat_frame = {}
    fund_grenze = 10
    cyclus_2_flag = False
    haupt_cyclus_flag = False

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
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        threshold = scene.get("marker_basis", 20)
        marker_adapt = scene.get("marker_adapt", 20)
        marker_plus = scene.get("marker_plus", 25)

        frames = low_marker_frame(scene, clip, threshold)

        if not frames:
            self.haupt_cyclus_flag = True
            self.report({'INFO'}, "Kein Frame mit zu wenigen Markern gefunden")
            return {'CANCELLED'}

        frame, count = frames[0]
        scene.frame_set(frame)

        # Wiederholungslogik
        if frame in self.repeat_frame:
            self.repeat_frame[frame] += 1

            if self.repeat_frame[frame] >= self.fund_grenze:
                test_cyclus()
                self.report(
                    {'INFO'},
                    f"Zyklus-Test ausgelöst nach {self.fund_grenze} Funden bei Frame {frame}",
                )
            else:
                adapt = max(marker_adapt * 1.1, 100)
                self.cyclus_2_flag = True
                self.report(
                    {'INFO'},
                    f"Erneut Frame {frame} gefunden ({self.repeat_frame[frame]}x) – adapt: {adapt:.2f}",
                )
        else:
            self.repeat_frame[frame] = 1
            adapt = min(marker_adapt * 0.9, marker_plus)
            self.cyclus_2_flag = True
            self.report(
                {'INFO'},
                f"Neuer Frame {frame} mit {count} Markern – adapt: {adapt:.2f}",
            )

        return {'FINISHED'}
