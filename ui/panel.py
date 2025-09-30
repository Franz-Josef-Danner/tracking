import bpy


class TRACKING_PT_tools_panel(bpy.types.Panel):
    bl_label = "Tracking Tools"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        layout = self.layout
        settings = getattr(context.scene, 'tracking_detect_settings', None)

        col = layout.column(align=True)
        col.operator('tracking.detect_markers', text='Detect Markers', icon='TRACKING')

        if settings is None:
            layout.label(text="[Warn] Settings fehlen", icon='ERROR')
            return

        box = layout.box()
        box.label(text="Duplikat-Filter & Optionen")
        col2 = box.column(align=True)
        col2.prop(settings, 'min_distance_px')
        col2.prop(settings, 'rounding_step')
        col2.prop(settings, 'use_overlap')
        if settings.use_overlap:
            col2.prop(settings, 'overlap_threshold')
        col2.prop(settings, 'tag_pass_names')
        col2.prop(settings, 'debug')
