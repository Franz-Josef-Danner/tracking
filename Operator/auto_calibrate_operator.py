# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable

# ---- Utility ---------------------------------------------------------------

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    """
    Setzt alle in UI/ui.py referenzierten Threshold-Properties auf 1.0.
    Wird von KAISERLICHTRACKER_OT_auto_calibrate aufgerufen.
    Idempotent; ignoriert fehlende Properties robust.
    """
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",            # ΔX-Threshold
        "kaiserlich_rot_thresh_y",            # ΔY-Threshold
        "kaiserlich_scale_thresh_min",        # Min Scale Δ
        "kaiserlich_scale_thresh_max",        # Max Scale Δ
        "kaiserlich_rot_scale_thresh_rot",    # Rot+Scale ΔRot
        "kaiserlich_rot_scale_thresh_scale",  # Rot+Scale ΔScale
        "kaiserlich_perspective_thresh",      # Perspective Δ
    )

    for p in props:
        if hasattr(scene, p):
            # hart auf 1.0 setzen; respektiert evtl. Min/Max-Clamps der FloatProperty
            try:
                setattr(scene, p, 1.0)
            except Exception:
                # Failsafe: kein Abriss der Pipeline, falls Property schreibgeschützt ist
                pass

# ---- Operator (Ausschnitt) ------------------------------------------------
# In deiner bestehenden Operator-Klasse einfach im execute() aufrufen:

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und führt danach Detect-Adapt und Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        set_all_thresholds_to_one(context)
        self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")
        return {'FINISHED'}
