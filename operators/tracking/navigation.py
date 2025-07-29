import bpy

from tracking_tools.helpers.set_playhead_to_frame import set_playhead_to_frame

class CLIP_OT_frame_jump_custom(bpy.types.Operator):
    bl_idname = "clip.frame_jump_custom"
    bl_label = "Frame Jump"
    bl_description = "Springt um 'Frames/Track' Frames vor"

    def execute(self, context):
        scene = context.scene
        step = getattr(scene, "frames_track", 1)
        frame = min(scene.frame_current + step, scene.frame_end)
        set_playhead_to_frame(scene, frame)
        return {'FINISHED'}


class CLIP_OT_marker_frame_plus(bpy.types.Operator):
    bl_idname = "clip.marker_frame_plus"
    bl_label = "Marker/Frame+"
    bl_description = "Erh\u00f6ht den Marker/Frame Wert"

    def execute(self, context):
        scene = context.scene
        scene.marker_frame += 1
        return {'FINISHED'}


class CLIP_OT_marker_frame_minus(bpy.types.Operator):
    bl_idname = "clip.marker_frame_minus"
    bl_label = "Marker/Frame-"
    bl_description = "Verringert den Marker/Frame Wert"

    def execute(self, context):
        scene = context.scene
        if scene.marker_frame > 1:
            scene.marker_frame -= 1
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_frame_jump_custom,
    CLIP_OT_marker_frame_plus,
    CLIP_OT_marker_frame_minus,
)
