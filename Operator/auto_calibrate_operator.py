# Operator/auto_calibrate_operator.py
import bpy
from typing import List, Any

# ---- Imports aus Helper ----------------------------------------------------
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_shorttest import short_test_track
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
#  MODAL AUTO-CALIBRATE OPERATOR
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Thresholds (Rot, Scale, Perspective)."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate (Modal)"
    bl_options = {"REGISTER", "INTERNAL"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks (Komma-getrennt)"
    )

    # interne Zustandsvariablen
    _timer = None
    _phase = 0
    _scene = None
    _ge_list = []
    _vals = {}
    _base = 0
    _step_keys = {}
    _done = False

    # ------------------------------------------------------------------------
    def execute(self, context):
        self._scene = context.scene
        self.report({'INFO'}, "[Kaiserlich Tracker][AutoCalibrate] Initialisierung...")
        set_all_thresholds_to_one(context)
        self.report({'INFO'}, "[AutoCalibrate] Thresholds auf 1.0 gesetzt.")
        self._phase = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'TIMER':
            try:
                if self._done:
                    self._finish(context)
                    return {'FINISHED'}

                if self._phase == 0:
                    self._run_short_test(context)
                elif self._phase == 1:
                    self._prepare_steps(context)
                elif self._phase == 2:
                    self._process_step(context, "STEP1", reduce_rot_xy, SCENE_DEEPTEST_ROT_XY_BEST)
                elif self._phase == 3:
                    self._process_step(context, "STEP2", reduce_scale_min_max, SCENE_DEEPTEST_SCALE_BEST)
                elif self._phase == 4:
                    self._process_step(context, "STEP3", reduce_rot_scale_pair, SCENE_DEEPTEST_ROT_SCALE_BEST)
                elif self._phase == 5:
                    self._process_step(context, "STEP4", reduce_perspective, SCENE_DEEPTEST_PERSPECTIVE_BEST)
                else:
                    self._done = True

            except Exception as e:
                self.report({'ERROR'}, f"[AutoCalibrate][Error] {e}")
                self._done = True
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def _run_short_test(self, context):
        names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
        result = short_test_track(context=context, tracks_to_delete=names,
                                  report_fn=lambda msg: self.report({'INFO'}, msg))
        self.report({'INFO'}, f"[AutoCalibrate] Short-Test abgeschlossen. Ergebnis: {result}")
        self._phase = 1

    # ------------------------------------------------------------------------
    def _prepare_steps(self, context):
        scene = self._scene
        self._base = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
        self._step_keys = {
            "STEP1": "kaiserlich_len_rot_xy_00",
            "STEP2": "kaiserlich_len_scale_00",
            "STEP3": "kaiserlich_len_rot_scale_00",
            "STEP4": "kaiserlich_len_perspective_0",
        }
        self._vals = {k: float(scene.get(p, 0)) for k, p in self._step_keys.items()}
        self._ge_list = [k for k, p in self._step_keys.items()
                         if float(scene.get(p, 0)) >= self._base]
        self.report({'INFO'}, f"[AutoCalibrate] Step-Vorbereitung abgeschlossen: {self._ge_list}")
        self._phase = 2

    # ------------------------------------------------------------------------
    def _process_step(self, context, key, reduce_fn, deeptest_key):
        if key not in self._ge_list:
            self._phase += 1
            return

        target = max(self._base, int(self._vals.get(key) or 0))
        self.report({'INFO'}, f"[AutoCalibrate] {key} → Ziel={target}")
        r = reduce_fn(context, target_len=target,
                      report_fn=lambda msg: self.report({'INFO'}, msg))
        self._scene[deeptest_key] = int(target)
        best = r.get("best", {})

        # Parameter-Update je nach Step
        if key == "STEP1" and best.get("values"):
            val = best["values"]
            set_scene_props(self._scene,
                kaiserlich_rot_thresh_x=float(val[0]),
                kaiserlich_rot_thresh_y=float(val[1]))
        elif key == "STEP2" and best.get("values"):
            val = best["values"]
            set_scene_props(self._scene,
                kaiserlich_scale_thresh_min=float(val[0]),
                kaiserlich_scale_thresh_max=float(val[1]))
        elif key == "STEP3" and best.get("values"):
            val = best["values"]
            set_scene_props(self._scene,
                kaiserlich_rot_scale_thresh_rot=float(val[0]),
                kaiserlich_rot_scale_thresh_scale=float(val[1]))
        elif key == "STEP4" and best.get("value") is not None:
            set_scene_props(self._scene,
                kaiserlich_perspective_thresh=float(best["value"]))

        self.report({'INFO'}, f"[AutoCalibrate] {key} abgeschlossen.")
        self._phase += 1

    # ------------------------------------------------------------------------
    def _finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.report({'INFO'}, "[AutoCalibrate] Alle Schritte abgeschlossen.")
        self._done = True

    # ------------------------------------------------------------------------
    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self.report({'INFO'}, "[AutoCalibrate] Abgebrochen.")


# ----------------------------------------------------------------------------
#  REGISTER / UNREGISTER
# ----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
