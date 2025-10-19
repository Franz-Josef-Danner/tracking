# Operator/auto_calibrate_operator.py
import bpy

DETECT_ADAPT_IDNAME = "kaiserlich_tracker.detect_adapt"  # ggf. an den realen bl_idname anpassen

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und triggert Detect/Adapt."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # --- 1) Alle relevanten Thresholds hart auf 1.0 setzen ---
        defaults = {
            "kaiserlich_rot_thresh_x": 1.0,
            "kaiserlich_rot_thresh_y": 1.0,
            "kaiserlich_scale_thresh_min": 1.0,
            "kaiserlich_scale_thresh_max": 1.0,
            "kaiserlich_rot_scale_thresh_rot": 1.0,
            "kaiserlich_rot_scale_thresh_scale": 1.0,
            "kaiserlich_perspective_thresh": 1.0,
        }

        missing = []
        for attr, val in defaults.items():
            if hasattr(scene, attr):
                setattr(scene, attr, val)
            else:
                missing.append(attr)

        if missing:
            # Nicht blockierend, nur Heads-up falls Properties noch nicht registriert sind
            self.report({'WARNING'}, f"Nicht gefundene Scene-Properties: {', '.join(missing)}")

        # Optional: sicherstellen, dass Änderungen sofort im UI ankommen
        # bpy.context.view_layer.update()

        # --- 2) Nach der Initialisierung: Detect/Adapt-Operator direkt ausführen ---
        # Ohne Popup/Extra-Fenster: EXEC_DEFAULT (nicht INVOKE_DEFAULT)
        try:
            result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
            # Falls der aufrufende Operator CANCELLED returned, sauber propagieren
            if {'CANCELLED'} in result:
                self.report({'ERROR'}, f"Operator {DETECT_ADAPT_IDNAME} wurde abgebrochen.")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Aufruf von {DETECT_ADAPT_IDNAME} fehlgeschlagen: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Übliche Registration, falls nicht bereits zentral geregelt
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

if __name__ == "__main__":
    register()
