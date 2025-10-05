import bpy


class KT_PT_panel(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_idname = "KT_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        # Panel nur anzeigen, wenn wir im Movie Clip Editor sind
        return context.space_data is not None and context.space_data.type == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, 'kt_marker_per_frame')
        col.operator('kt.detect_cyclus', icon='TRACKING_FORWARDS')


classes = (KT_PT_panel,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
