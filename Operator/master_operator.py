import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.low_marker_frame import find_first_weak_frame

class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich.master_operator"
    bl_label = "Master Operator"
    bl_description = "Setzt den Playhead auf den ersten Frame mit der geringsten Markeranzahl"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        frame = find_first_weak_frame(context)

        if frame is None:
            self.report({'INFO'}, "[Master] Kein schwacher Frame gefunden oder Marker-Ziel nicht unterschritten.")
            print("[Kaiserlich Tracker][Master] Kein schwacher Frame gefunden oder Marker-Ziel nicht unterschritten.")
            return {'CANCELLED'}

        print(f"[Kaiserlich Tracker][Master] Playhead gesetzt auf Frame {frame} (geringste Markeranzahl).")
        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt.")
        return {'FINISHED'}

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_operator)