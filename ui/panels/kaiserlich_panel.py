import bpy


class CLIP_PT_kaiserlich(bpy.types.Panel):
    bl_label = "Kaiserlich"
    bl_idname = "CLIP_PT_kaiserlich"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and context.space_data.mode == 'TRACKING'
        )

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "marker_basis")
        layout.prop(scene, "frames_per_track")
        layout.prop(scene, "error_per_track")
        row = layout.row()
        row.enabled = context.space_data.clip is not None
        row.operator("clip.kaiserlich_track", text="Track")
