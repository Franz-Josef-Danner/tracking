import bpy
from typing import Dict, List, Tuple


# -----------------------------------------------------------------------------
# Helper: Sammeln der Kalibrier-Thresholds aus der Szene (UI-Eingaben)
# -----------------------------------------------------------------------------

def get_calibration_thresholds(context) -> List[Tuple[str, float]]:
    """Liest alle UI-Threshold-Felder aus ``UI/ui.py`` und gibt sie als Liste
    von (key, value) Tupeln zurück.

    Die Keys sind bewusst kurz & sprechend gehalten, damit sie z. B. in Logs
    oder weiteren Helpern gut verwendbar sind.
    """
    scene = context.scene

    # Fallbacks mit 0.0, falls die UI-Properties noch nicht registriert wären.
    def _f(name: str) -> float:
        return float(getattr(scene, name, 0.0))

    thresholds: List[Tuple[str, float]] = [
        ("rot_thresh_x", _f("kaiserlich_rot_thresh_x")),
        ("rot_thresh_y", _f("kaiserlich_rot_thresh_y")),
        ("scale_thresh_min", _f("kaiserlich_scale_thresh_min")),
        ("scale_thresh_max", _f("kaiserlich_scale_thresh_max")),
        ("rot_scale_thresh_rot", _f("kaiserlich_rot_scale_thresh_rot")),
        ("rot_scale_thresh_scale", _f("kaiserlich_rot_scale_thresh_scale")),
    ]
    return thresholds


# -----------------------------------------------------------------------------
# Operator: Auto‑Calibrate Thresholds
# -----------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Legt eine Threshold-Liste aus den UI-Eingabefeldern an und speichert
    sie in der Szene unter ``scene["kaiserlich_calibration_thresholds"]``.

    Weitere Kalibrierlogik (z. B. automatisches Tuning) kann auf dieser Liste
    aufbauen.
    """

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Erfasst aktuelle Threshold-UI-Werte und legt eine Kalibrier-Liste an."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        thresholds = get_calibration_thresholds(context)

        # Für nachgelagerte Operatoren/Helper auch als Mapping ablegen:
        as_dict: Dict[str, float] = {k: v for k, v in thresholds}
        scene = context.scene
        scene["kaiserlich_calibration_thresholds"] = as_dict  # ID-Property

        # Kurzes Log/Feedback
        pretty = ", ".join(f"{k}={v:.6f}" for k, v in thresholds)
        self.report({'INFO'}, f"Calibration Thresholds erfasst: {pretty}")
        print("[Kaiserlich Tracker][Auto-Calibrate]", pretty)

        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Registrierung
# -----------------------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()
