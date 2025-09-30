import bpy

class TRACKING_PT_tools_panel(bpy.types.Panel):
    bl_label = "Tracking Tools"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        op = col.operator('tracking.detect_markers', text='Detect Markers', icon='TRACKING')
        # Sektion für Einstellungen
        box = layout.box()
        box.label(text="Duplikat-Filter")
        box.prop(context.scene, 'tracking_min_distance_dummy', text="(nutzt Operator-Werte)")  # Platzhalter falls später Szene-Props nötig
        col2 = box.column(align=True)
        col2.prop(op, 'min_distance_px')
        col2.prop(op, 'use_overlap')
        if op.use_overlap:
            col2.prop(op, 'overlap_threshold')
        col2.prop(op, 'rounding_step')
        col2.prop(op, 'tag_pass_names')
        col2.prop(op, 'debug')
