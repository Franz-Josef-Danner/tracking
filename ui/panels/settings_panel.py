import bpy
import os

from ...helpers.step_introspection import get_step_methods_with_calls


def get_tracking_steps_info() -> list:
    """Return step method info from the tracking operator source file."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(base, "operators", "tracking", "cycle.py")
    return get_step_methods_with_calls(os.path.abspath(path))

class CLIP_PT_final_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Final'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'marker_frame', text='Marker/Frame')
        layout.prop(context.scene, 'frames_track', text='Frames/Track')
        layout.prop(context.scene, 'error_threshold', text='Error Threshold')


class CLIP_PT_stufen_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Stufen'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.proxy_build', text='Proxy erstellen (50%)')
        layout.operator('clip.track_nr1', text='Track Nr. 1')
        layout.label(text="Automatischer Ablauf:")
        for step in get_tracking_steps_info():
            box = layout.box()
            box.label(text=f"{step['name']} – {step['doc']}")
            for call in step['calls']:
                box.label(text=f"\u21b3 {call}", icon='DOT')
        layout.operator('clip.cleanup', text='Cleanup')
        layout.operator('clip.track_nr2', text='Track Nr. 2')


panel_classes = (
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
)
