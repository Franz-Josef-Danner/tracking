import bpy


class TRACK_PT_test(bpy.types.Panel):
    bl_label = "Test"
    bl_idname = "TRACK_PT_test"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"

    def draw(self, context):
        pass


class TRACK_PT_test_details(bpy.types.Panel):
    bl_label = "Test Details"
    bl_idname = "TRACK_PT_test_details"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"
    bl_parent_id = "TRACK_PT_test"

    def draw(self, context):
        layout = self.layout
        layout.operator("track.test_default", text="Test Default")


panel_classes = (
    TRACK_PT_test,
    TRACK_PT_test_details,
)
