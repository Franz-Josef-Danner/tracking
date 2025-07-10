import bpy
from .Combine import find_sparse_marker_frames


class CLIP_OT_find_sparse_marker_frames(bpy.types.Operator):
    bl_idname = "clip.find_sparse_marker_frames"
    bl_label = "Finde Frames mit <10 Marker"
    bl_description = (
        "Durchsuche Frames und gib die mit weniger als 10 aktiven Markern aus"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein Clip im Editor geladen.")
            return {'CANCELLED'}

        threshold = max(1, context.scene.min_marker_count)
        frames_with_few_markers = find_sparse_marker_frames(clip, threshold)

        for frame, count in frames_with_few_markers:
            print(f"Frame {frame}: {count} aktive Marker")

        self.report({'INFO'}, f"{len(frames_with_few_markers)} Frames gefunden.")
        return {'FINISHED'}


class CLIP_PT_marker_check_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Marker Analyse'
    bl_label = 'Marker Analyse'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.find_sparse_marker_frames", icon='VIEWZOOM')


classes = (CLIP_OT_find_sparse_marker_frames, CLIP_PT_marker_check_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
