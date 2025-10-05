import bpy
from ..Helper import bootstrap

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = 'kaiserlich.detect_cyclus'
    bl_label = 'Detect Cyclus'
    bl_description = 'Erkennt den Zyklus basierend auf den Einstellungen'

    def execute(self, context):
        scene = context.scene
        # Sicherstellen, dass Property existiert
        props = getattr(scene, 'kaiserlich_tracker', None)
        if props is None or not hasattr(props, 'marker_per_frame'):
            self.report({'ERROR'}, 'Property marker_per_frame nicht gefunden – bitte Add-on neu laden.')
            return {'CANCELLED'}

        ef_raw = props.marker_per_frame
        try:
            ef = int(ef_raw)
        except Exception:
            self.report({'ERROR'}, f'Ungueltiger Eingabewert: {ef_raw}')
            return {'CANCELLED'}

        bootstrap.run(context, ef)
        self.report({'INFO'}, f'Berechnung gestartet mit Eingabewert {ef}')
        return {'FINISHED'}

classes = (KAISERLICH_OT_detect_cyclus,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
