import bpy


class KT_PT_panel(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_idname = "KT_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        params = getattr(scene, 'kt_params', None)

        if params is None:
            layout.label(text="Parameter nicht initialisiert")
            return

        box_in = layout.box()
        box_in.label(text="Eingabe")
        box_in.prop(params, 'marker_per_frame')
        box_in.operator('kt.detect_cyclus', icon='TRACKING_FORWARDS')

        box_out = layout.box()
        box_out.label(text="Berechnete Werte")
        grid = box_out.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True)
        # Anzeige wichtiger Parameter
        for attr in ('hz', 'vc', 'pz', 'sz', 'og', 'ug', 'md', 'ma', 'za', 'tr'):
            row = grid.row()
            row.label(text=f"{attr}:")
            val = getattr(params, attr)
            row.label(text=str(val))


classes = (KT_PT_panel,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
