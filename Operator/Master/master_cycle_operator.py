# Operator/master_cycle_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame

class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Setzt den Playhead auf den ersten Frame mit der geringsten Markeranzahl"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # Wenn kein Frame gefunden wurde → regulär beenden
        # ------------------------------------------------------------------
        if frame is None:
            self.report({'INFO'}, "[Master] Kein schwacher Frame gefunden oder Marker-Ziel nicht unterschritten.")
            print("[Kaiserlich Tracker][Master] Kein schwacher Frame gefunden – ShortTest wird NICHT gestartet.")
            return {'FINISHED'}

        # ------------------------------------------------------------------
        # Wenn ein Frame gefunden wurde → Playhead setzen und ShortTest starten
        # ------------------------------------------------------------------
        scene = context.scene
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        print(f"[Kaiserlich Tracker][Master] Playhead gesetzt auf Frame {frame} – Starte ShortTest.")
        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt – ShortTest wird gestartet.")

        # Operator-Aufruf (vollständiger ShortTest)
        # Erwartete ID: bl_idname = "kaiserlich_tracker.master_shorttest_operator"
        op_id = "kaiserlich_tracker.master_shorttest_operator"
        try:
            # Sanity-Check: Ist der Operator registriert?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_shorttest_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_shorttest_operator.py"
                print(f"[Kaiserlich Tracker][Master] ⚠️ {msg}")
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            # Start
            bpy.ops.kaiserlich_tracker.master_shorttest_operator('INVOKE_DEFAULT')
            print("[Kaiserlich Tracker][Master] ShortTest erfolgreich gestartet.")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][Master] ⚠️ Fehler beim Starten des ShortTest: {ex!r}")
            self.report({'WARNING'}, f"Fehler beim Start des ShortTest: {ex}")

        return {'FINISHED'}

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
