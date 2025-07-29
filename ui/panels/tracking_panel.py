import bpy

from .settings_panel import get_tracking_steps_info

class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon Informationen")


class CLIP_PT_tracking_steps(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Tracking Schritte'

    def draw(self, context):
        layout = self.layout

        layout.operator('clip.track_nr1', text='Track Nr. 1')

        layout.label(text="Automatischer Ablauf:")
        box = layout.box()
        for name, desc in get_tracking_steps_info():
            box.label(text=f"{name} \u2013 {desc}")


panel_classes = (
    CLIP_PT_tracking_panel,
    CLIP_PT_tracking_steps,
)
