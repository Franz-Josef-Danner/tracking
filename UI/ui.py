import bpy

class KAISERLICHTRACKER_PT_panel(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_idname = "KAISERLICH_TRACKER_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_markers_per_frame", text="Marker per Frame")
        col.operator("kaiserlich_tracker.detect_cycle", text="Detect Cyclus")
        col.operator("kaiserlich_tracker.track_cycle", text="Track bis Szenen-Ende")
