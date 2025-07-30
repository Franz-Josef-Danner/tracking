import bpy

from ..helpers.low_marker_frame import low_marker_frame


class CLIP_OT_low_marker_frame(bpy.types.Operator):
    """Springt zum ersten Frame mit zu wenigen Markern"""

    bl_idname = "clip.low_marker_frame"
    bl_label = "Low Marker Frame"
    bl_description = "Springe zum ersten Frame mit weniger Markern als Marker/Frame"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        threshold = scene.get("marker_basis", 20)

        frames = low_marker_frame(scene, clip, threshold)
        if not frames:
            self.report({'INFO'}, "Kein Frame mit zu wenigen Markern gefunden")
            return {'CANCELLED'}

        frame, count = frames[0]
        scene.frame_set(frame)
        self.report({'INFO'}, f"Frame {frame} mit {count} Markern")
        return {'FINISHED'}
