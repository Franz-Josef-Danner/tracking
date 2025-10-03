import bpy


class CLIP_PT_KaiserlichTracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_marker_per_frame")
        col.operator("clip.kaiserlich_detect_cycle", icon="TRACKING_FORWARDS")

        box = layout.box()
        box.label(text="Status")
        row = box.row(align=True)
        row.prop(scene, "kaiserlich_last_marker_count", text="Letzte Anzahl")
        row.enabled = False
        if scene.kaiserlich_cycle_running:
            box.label(text="Läuft...", icon="TIME")
        else:
            box.label(text="Bereit", icon="CHECKMARK")
