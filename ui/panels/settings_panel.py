import bpy
import os

from ...helpers.step_order import extract_step_sequence_from_cycle


def get_fsm_sequence() -> list:
    """Return the FSM step sequence from the tracking operator source file."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(base, "operators", "tracking", "cycle.py")
    return extract_step_sequence_from_cycle(os.path.abspath(path))

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
        layout.label(text="Automatischer Ablauf:")
        for key in get_fsm_sequence():
            box = layout.box()
            box.label(text=key)


panel_classes = (
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
)
