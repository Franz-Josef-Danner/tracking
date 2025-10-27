# Operator/auto_calibrate_operator.py
import bpy
from typing import List, Any

# ---- Imports aus Helper ----------------------------------------------------
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_shorttest import short_test_track     # <-- angepasst
from ..Helper.util_scene import set_scene_props
from ..Helper.util_reduce import (
    reduce_rot_xy,
    reduce_scale_min_max,
    reduce_rot_scale_pair,
    reduce_perspective,
)
from ..Helper.util_shorttest import SCENE_TOTAL_TRACK_LEN_BASE
from ..Helper.util_deeptest import (
    SCENE_DEEPTEST_ROT_XY_BEST,
    SCENE_DEEPTEST_SCALE_BEST,
    SCENE_DEEPTEST_ROT_SCALE_BEST,
    SCENE_DEEPTEST_PERSPECTIVE_BEST,
)


# ----------------------------------------------------------------------------
#  OPERATOR
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Thresholds (Rot, Scale, Perspective)."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks (Komma-getrennt)"
    )

    # ------------------------------------------------------------------------
    #  EXECUTE
    # ------------------------------------------------------------------------
    def execute(self, context):
        report = lambda msg: self.report({'INFO'}, msg)
        scene = context.scene

        try:
            # --- 1) RESET THRESHOLDS ---------------------------------------
            set_all_thresholds_to_one(context)
            report("Kaiserlich Tracker: Thresholds auf 1.0 gesetzt.")

            # --- 2) SHORT TEST (vereint) -----------------------------------
            names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
            result = short_test_track(context=context, tracks_to_delete=names, report_fn=report)
            report(f"Short-Test abgeschlossen. Ergebnis: {result}")

            # Nach short_test_track liegen alle Längenwerte bereits in der Szene
            base = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
            step_keys = {
                "STEP1": "kaiserlich_len_rot_xy_00",
                "STEP2": "kaiserlich_len_scale_00",
                "STEP3": "kaiserlich_len_rot_scale_00",
                "STEP4": "kaiserlich_len_perspective_0",
            }

            # Liste der verbesserten oder gültigen Steps bestimmen
            ge_list = [
                key for key, prop in step_keys.items()
                if float(scene.get(prop, 0)) >= base
            ]

            # --- 3) LONG TESTS ---------------------------------------------
            vals = {key: float(scene.get(prop, 0)) for key, prop in step_keys.items()}

            # STEP 1 – ROT/XY (gekoppelt)
            if "STEP1" in ge_list:
                target = max(base, int(vals.get("STEP1") or 0))
                r = reduce_rot_xy(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_XY_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_rot_thresh_x=float(val[0]),
                        kaiserlich_rot_thresh_y=float(val[1]))
                    ratio = best.get("ratio")
                    report(f"[Reduce RotXY] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])}) "
                           f"{'(ratio='+fmt8(ratio)+')' if ratio else ''}")

            # STEP 2 – SCALE MIN/MAX (gekoppelt)
            if "STEP2" in ge_list:
                target = max(base, int(vals.get("STEP2") or 0))
                r = reduce_scale_min_max(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_SCALE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_scale_thresh_min=float(val[0]),
                        kaiserlich_scale_thresh_max=float(val[1]))
                    report(f"[Reduce Scale] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])})")

            # STEP 3 – ROT + SCALE PAIR
            if "STEP3" in ge_list:
                target = max(base, int(vals.get("STEP3") or 0))
                r = reduce_rot_scale_pair(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_SCALE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_rot_scale_thresh_rot=float(val[0]),
                        kaiserlich_rot_scale_thresh_scale=float(val[1]))
                    report(f"[Reduce Rot+Scale] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])})")

            # STEP 4 – PERSPECTIVE
            if "STEP4" in ge_list:
                target = max(base, int(vals.get("STEP4") or 0))
                r = reduce_perspective(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("value")
                if best.get("sf") and val is not None:
                    set_scene_props(scene, kaiserlich_perspective_thresh=float(val))
                    report(f"[Reduce Perspective] sf={fmt8(best['sf'])} "
                           f"→ {fmt8(val)}")

            # --- 4) FINAL SUCCESS ------------------------------------------
            report("Auto-Calibrate erfolgreich abgeschlossen.")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}


# ----------------------------------------------------------------------------
#  REGISTER / UNREGISTER
# ----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
