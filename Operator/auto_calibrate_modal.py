# Operator/auto_calibrate_modal.py
import bpy
from ..Operator.auto_calibrate_operator import (
    short_test_pipeline,
    compare_len_steps_to_total,
    reduce_rot_xy,
    reduce_scale_min_max,
    reduce_rot_scale_pair,
    reduce_perspective,
    set_all_thresholds_to_one,
    _fmt8,
    SCENE_DEEPTEST_ROT_XY_BEST,
    SCENE_DEEPTEST_SCALE_BEST,
    SCENE_DEEPTEST_ROT_SCALE_BEST,
    SCENE_DEEPTEST_PERSPECTIVE_BEST,
    _set_scene_props
)


class KAISERLICHTRACKER_OT_auto_calibrate_modal(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate_modal"
    bl_label = "Kaiserlich Tracker – Auto Calibrate (Modal)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    _state = "INIT"
    _timer = None
    _result_cache = {}
    _cmp_result = None

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._state = "INIT"
        print("[Kaiserlich Tracker][AutoCalibrate] Modal gestartet.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._state == "INIT":
            set_all_thresholds_to_one(context)
            print("[AutoCalibrate] Thresholds => 1.0")
            try:
                self._result_cache = short_test_pipeline(context=context)
                self._state = "EVAL"
                print("[AutoCalibrate] Short-Test-Pipeline abgeschlossen.")
            except Exception as e:
                self.report({'ERROR'}, f"Short-Test-Pipeline fehlgeschlagen: {e}")
                return self._stop(context, cancelled=True)
            return {'RUNNING_MODAL'}

        elif self._state == "EVAL":
            try:
                self._cmp_result = compare_len_steps_to_total(context)
                self._ge_list = self._cmp_result.get("better_or_equal", [])
                print("[AutoCalibrate] Vergleich abgeschlossen.")
                self._state = "REDUCE_ROT_XY"
            except Exception as e:
                self.report({'ERROR'}, f"Vergleich fehlgeschlagen: {e}")
                return self._stop(context, cancelled=True)
            return {'RUNNING_MODAL'}

        elif self._state == "REDUCE_ROT_XY":
            if "STEP1" in self._ge_list:
                try:
                    scene = context.scene
                    base = int(self._cmp_result.get("baseline") or 0)
                    v = int(self._cmp_result["values"].get("STEP1") or 0)
                    target_len = max(base, v)
                    res = reduce_rot_xy(context, target_len=target_len)
                    best = res.get("best", {})
                    scene[SCENE_DEEPTEST_ROT_XY_BEST] = int(target_len)
                    vals = best.get("values")
                    if vals:
                        _set_scene_props(scene,
                            kaiserlich_rot_thresh_x=float(vals[0]),
                            kaiserlich_rot_thresh_y=float(vals[1]))
                        print(f"[Reduce RotXY] sf={_fmt8(best.get('sf'))} thr={_fmt8(vals[0])},{_fmt8(vals[1])}")
                except Exception as e:
                    print(f"[Reduce RotXY] Fehler: {e}")
            self._state = "REDUCE_SCALE"
            return {'RUNNING_MODAL'}

        elif self._state == "REDUCE_SCALE":
            if "STEP2" in self._ge_list:
                try:
                    scene = context.scene
                    base = int(self._cmp_result.get("baseline") or 0)
                    v = int(self._cmp_result["values"].get("STEP2") or 0)
                    target_len = max(base, v)
                    res = reduce_scale_min_max(context, target_len=target_len)
                    best = res.get("best", {})
                    scene[SCENE_DEEPTEST_SCALE_BEST] = int(target_len)
                    vals = best.get("values")
                    if vals:
                        _set_scene_props(scene,
                            kaiserlich_scale_thresh_min=float(vals[0]),
                            kaiserlich_scale_thresh_max=float(vals[1]))
                        print(f"[Reduce Scale] sf={_fmt8(best.get('sf'))} thr={_fmt8(vals[0])},{_fmt8(vals[1])}")
                except Exception as e:
                    print(f"[Reduce Scale] Fehler: {e}")
            self._state = "REDUCE_ROT_SCALE"
            return {'RUNNING_MODAL'}

        elif self._state == "REDUCE_ROT_SCALE":
            if "STEP3" in self._ge_list:
                try:
                    scene = context.scene
                    base = int(self._cmp_result.get("baseline") or 0)
                    v = int(self._cmp_result["values"].get("STEP3") or 0)
                    target_len = max(base, v)
                    res = reduce_rot_scale_pair(context, target_len=target_len)
                    best = res.get("best", {})
                    scene[SCENE_DEEPTEST_ROT_SCALE_BEST] = int(target_len)
                    vals = best.get("values")
                    if vals:
                        _set_scene_props(scene,
                            kaiserlich_rot_scale_thresh_rot=float(vals[0]),
                            kaiserlich_rot_scale_thresh_scale=float(vals[1]))
                        print(f"[Reduce Rot+Scale] sf={_fmt8(best.get('sf'))} thr={_fmt8(vals[0])},{_fmt8(vals[1])}")
                except Exception as e:
                    print(f"[Reduce Rot+Scale] Fehler: {e}")
            self._state = "REDUCE_PERSPECTIVE"
            return {'RUNNING_MODAL'}

        elif self._state == "REDUCE_PERSPECTIVE":
            if "STEP4" in self._ge_list:
                try:
                    scene = context.scene
                    base = int(self._cmp_result.get("baseline") or 0)
                    v = int(self._cmp_result["values"].get("STEP4") or 0)
                    target_len = max(base, v)
                    res = reduce_perspective(context, target_len=target_len)
                    best = res.get("best", {})
                    scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = int(target_len)
                    val_ = best.get("value")
                    if val_ is not None:
                        _set_scene_props(scene, kaiserlich_perspective_thresh=float(val_))
                        print(f"[Reduce Perspective] sf={_fmt8(best.get('sf'))} thr={_fmt8(val_)}")
                except Exception as e:
                    print(f"[Reduce Perspective] Fehler: {e}")
            self._state = "DONE"
            return {'RUNNING_MODAL'}

        elif self._state == "DONE":
            print("[AutoCalibrate] ✅ Kalibrierung vollständig abgeschlossen.")
            return self._stop(context)

        return {'RUNNING_MODAL'}

    def _stop(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        print("[AutoCalibrate] Modal beendet." if not cancelled else "[AutoCalibrate] Abgebrochen.")
        return {'FINISHED' if not cancelled else 'CANCELLED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate_modal)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate_modal)
