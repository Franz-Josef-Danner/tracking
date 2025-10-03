import bpy
from ..Helper import bootstrap, snapshot, detect

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = "kaiserlich.detect_cycle"  # ID bleibt technisch gleich für Kompatibilität
    bl_label = "Detect Cyclus"
    bl_description = "Führt den Erkennungs-Cyclus aus"

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_marker_per_frame
        # 1) Parameter berechnen
        params = bootstrap.run(context, ef)
        # 2) Snapshot der aktuell aktiven Marker aufnehmen
        markers = snapshot.capture_current_frame_markers(context)
        # 3) Feature Detection mit tr, md, ma, pz, sz
        detect.detect_features(context, params)
        tr = params.get('tr')
        md = params.get('md')
        ma = params.get('ma')
        pz = params.get('pz')
        sz = params.get('sz')
        self.report({'INFO'}, (
            f"Detect Cyclus fertig: {len(markers)} Marker | ef={ef} "
            f"tr={tr} md={md} ma={ma} pz={pz} sz={sz}"
        ))
        return {'FINISHED'}

classes = [KAISERLICH_OT_detect_cyclus]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
