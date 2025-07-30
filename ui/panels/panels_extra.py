import bpy

class CLIP_PT_test_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'API Funktionen'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Initialisierung:")
        layout.operator("tracking.set_default_settings")
        

class CLIP_PT_test_subpanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_parent_id = 'CLIP_PT_test_panel'
    bl_label = 'Test'

    def draw(self, context):
        layout = self.layout
        # Unterpanel ohne Buttons
        

class CLIP_PT_test_detail_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_parent_id = 'CLIP_PT_test_subpanel'
    bl_label = 'Details'

    def draw(self, context):
        layout = self.layout
        # Keine weiteren Bedienelemente


panel_classes = (
    CLIP_PT_test_panel,
    CLIP_PT_test_subpanel,
    CLIP_PT_test_detail_panel,
)
