import bpy
import inspect

from ...operators.tracking.cycle import CLIP_OT_track_nr1


def get_tracking_steps_info():
    """Return (name, doc) pairs for all step_ methods in CLIP_OT_track_nr1."""
    steps = []
    for name, method in inspect.getmembers(CLIP_OT_track_nr1, predicate=inspect.isfunction):
        if name.startswith("step_"):
            doc = inspect.getdoc(method) or "Keine Beschreibung vorhanden"
            first_line = doc.splitlines()[0] if doc else ""
            steps.append((name, first_line))
    return steps

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
        box = layout.box()
        for name, desc in get_tracking_steps_info():
            box.label(text=f"{name} – {desc}")
        layout.operator('clip.cleanup', text='Cleanup')
        layout.operator('clip.track_nr2', text='Track Nr. 2')


panel_classes = (
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
)
