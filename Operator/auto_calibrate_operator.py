import bpy
from typing import List, Any

# ---- Imports aus Helper ----------------------------------------------------
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_shorttest import short_test_pipeline, compare_len_steps_to_total
from ..Helper.util_scene import set_scene_props
from ..Helper.util_reduce import (
    reduce_rot_xy,
    reduce_scale_min_max,
    reduce_rot_scale_pair,
    reduce_perspective,
)
from ..Helper.util_shorttest import (
    SCENE_TOTAL_TRACK_LEN_BASE,
)
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
        try:
            report = lambda msg: self.report({'INFO'}, msg)
            scene = context.scene

            # --- 1) RESET THRESHOLDS ---------------------------------------
            set_all_thresholds_to_one(context)
            report("Kaiserlich Tracker: Thresholds auf 1.0 gesetzt.")

            # --- 2) SHORT-TEST PIPELINE ------------------------------------
            try:
                names: List[str] = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
                results = short_test_pipeline(context=context, tracks_to_delete=names, report_fn=report)

                report(f"Short-Test abgeschlossen | "
                       f"Base={results['baseline']} | "
                       f"Step1={results['step1']} | "
                       f"Step2={results['step2']} | "
                       f"Step3={results['step3']} | "
                       f"Step4={results['step4']}")
            except Exception as e:
                self.report({'ERROR'}, f"Short-Test fehlgeschlagen: {e}")
                return {'CANCELLED'}

            # --- 3) VERGLEICH ------------------------------------------------
            cmp = compare_len_steps_to_total(context)
            base = int(cmp.get("baseline") or 0)
            vals = cmp.get("values", {})
            rels = cmp.get("relations", {})
            ge_list = cmp.get("better_or_equal", [])

            report(f"Vergleich: Base={base} | "
                   f"Step1={vals.get('STEP1')}({rels.get('STEP1')}) "
                   f"Step2={vals.get('STEP2')}({rels.get('STEP2')}) "
                   f"Step3={vals.get('STEP3')}({rels.get('STEP3')}) "
                   f"Step4={vals.get('STEP4')}({rels.get('STEP4')})")
            report("≥ Baseline: " + (", ".join(ge_list) if ge_list else "keine"))

            # --- 4) LONG TESTS ---------------------------------------------
            # STEP 1 – ROT/XY (gekoppelt, X-only)
            if "STEP1" in ge_list:
                try:
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
                except Exception as e:
                    self.report({'WARNING'}, f"STEP1 RotXY-Reducer: {e}")

            # STEP 2 – SCALE MIN/MAX (gekoppelt)
            if "STEP2" in ge_list:
                try:
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
                except Exception as e:
                    self.report({'WARNING'}, f"STEP2 Scale-Reducer: {e}")

            # STEP 3 – ROT + SCALE PAIR
            if "STEP3" in ge_list:
                try:
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
                except Exception as e:
                    self.report({'WARNING'}, f"STEP3 RotScale-Reducer: {e}")

            # STEP 4 – PERSPECTIVE
            if "STEP4" in ge_list:
                try:
                    target = max(base, int(vals.get("STEP4") or 0))
                    r = reduce_perspective(context, target_len=target, report_fn=report)
                    scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = int(target)
                    best = r.get("best", {})
                    val = best.get("value")
                    if best.get("sf") and val is not None:
                        set_scene_props(scene, kaiserlich_perspective_thresh=float(val))
                        report(f"[Reduce Perspective] sf={fmt8(best['sf'])} "
                               f"→ {fmt8(val)}")
                except Exception as e:
                    self.report({'WARNING'}, f"STEP4 Perspective-Reducer: {e}")

            # --- 5) FINAL SUCCESS ------------------------------------------
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