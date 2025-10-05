import bpy
from ..Helper import bootstrap, snapshot, newmarker, detect, compare

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

        values = bootstrap.run(context, ef)
        if not values:
            self.report({'ERROR'}, 'Keine Berechnungen – kein aktiver Clip?')
            return {'CANCELLED'}

        # Zyklus / Pipeline Schritte
        print('--- Zyklus Start (snapshot) ---')
        snapshot.run(context, values)
        print('--- Neue Marker Vorbereitung ---')
        newmarker.run(context, values)
        print('--- Feature Detection ---')
        detect.run(context, tr=values['tr'], md=values['md'], ma=values['ma'])
        print('--- Marker Vergleich ---')
        compare.run(context)

        self.report({'INFO'}, f'Zyklus ausgeführt (ef={ef})')
        return {'FINISHED'}

classes = (KAISERLICH_OT_detect_cyclus,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
