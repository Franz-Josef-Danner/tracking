# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator

# --- Helper ---------------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
    from ...Helper.refine_intrinsics import (
        refine_intrinsics_reset,
        refine_intrinsics_focal_length_on,
        refine_intrinsics_principal_point_on,
        refine_intrinsics_radial_distortion_on,
    )
    from ...Helper.low_marker_frame import find_first_weak_frame
    from ...Helper.clean_error_tracks import clean_error_tracks
except Exception as e:
    raise ImportError(f"[master_resolve_operator] Missing add-on modules: {e}")


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Deterministische 4-Stage Resolve-Pipeline ohne Modal-Deadlocks"""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = self._get_clip(context)
        if clip is None:
            print("[Resolve] Kein Clip → CANCEL")
            return {'CANCELLED'}

        print("\n================= Resolve Master Start =================")

        # Stage 0 ----------------------------------------------------
        if not self._run_stage(
            context, clip,
            threshold=10.0,
            refine_focal=False,
            refine_pp=False,
            refine_radial=False,
            next_stage="STAGE1"
        ):
            return {'FINISHED'}

        # Stage 1 ----------------------------------------------------
        max_err = self._max_err(context)
        if not self._run_stage(
            context, clip,
            threshold=max_err,
            refine_focal=True,
            refine_pp=False,
            refine_radial=False,
            next_stage="STAGE2"
        ):
            return {'FINISHED'}

        # Stage 2 ----------------------------------------------------
        if not self._run_stage(
            context, clip,
            threshold=max_err,
            refine_focal=True,
            refine_pp=True,
            refine_radial=False,
            next_stage="STAGE3"
        ):
            return {'FINISHED'}

        # Stage 3 ----------------------------------------------------
        if not self._run_stage(
            context, clip,
            threshold=max_err,
            refine_focal=True,
            refine_pp=True,
            refine_radial=True,
            next_stage=None
        ):
            return {'FINISHED'}

        print("================= Resolve Master Ende =================")
        return {'FINISHED'}

    # -------------------------------------------------------------

    def _run_stage(self, context, clip, threshold, refine_focal, refine_pp, refine_radial, next_stage):
        print(f"\n[Resolve] Stage (F:{refine_focal} PP:{refine_pp} R:{refine_radial})")

        refine_intrinsics_reset(context)
        if refine_focal:
            refine_intrinsics_focal_length_on(context)
        if refine_pp:
            refine_intrinsics_principal_point_on(context)
        if refine_radial:
            refine_intrinsics_radial_distortion_on(context)

        if not self._solve(context):
            print("[Resolve] Solve fehlgeschlagen → ABORT")
            return False

        avg_err = get_average_error(clip)
        print(f"[Resolve] avg={avg_err} threshold={threshold}")

        if avg_err is None or avg_err != avg_err:
            print("[Resolve] avg ungültig → ABORT")
            return False

        if avg_err <= threshold:
            print("[Resolve] threshold erreicht → FINISH")
            return False

        # Cleanup für > threshold
        deleted = clean_error_tracks(context, sort_desc=True)
        print(f"[Resolve] Deleted = {deleted}")

        weak = find_first_weak_frame(context)
        if weak is None:
            if next_stage:
                print("[Resolve] → Nächste Stage")
                return True
            print("[Resolve] → FINISH (last stage, keine weak frames)")
            return False

        print(f"[Resolve] Weak Frame @ {weak} → Übergabe an Master Cycle")
        bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
        return False

    # -------------------------------------------------------------

    def _solve(self, context):
        try:
            bpy.ops.clip.solve_camera('EXEC_DEFAULT')
        except Exception as e:
            print(f"[Resolve] Solve Fehler: {e}")
            return False
        print("[Resolve] Solve OK")
        return True

    def _get_clip(self, context):
        space = context.space_data
        return getattr(space, "clip", None)

    def _max_err(self, context):
        try:
            return float(getattr(context.scene, "max_error_value"))
        except:
            return 2.0


# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
