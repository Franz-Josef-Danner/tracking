# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator, Context

# -----------------------------
# Helper Imports
# -----------------------------
from ...Helper.refine_intrinsics import (
    refine_intrinsics_reset,
    refine_intrinsics_focal_length_on,
    refine_intrinsics_principal_point_on,
    refine_intrinsics_radial_distortion_on,
)
from ...Helper.clean_error_tracks import clean_error_tracks
from ...Helper.get_average_error import get_average_error
from ...Helper.low_marker_frame import find_first_weak_frame


def _cycle_1(context):
    # TODO: Hier den echten Operator rein, aktuell Dummy
    print("[Resolve] → cycle_1()")
    bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')


def _solve(context):
    print("[Resolve] → Solve Camera")
    bpy.ops.clip.solve_camera()


def _kpi_cleanup(context, clip, limit: float):
    err = get_average_error(clip)
    print(f"[Resolve] KPI Error: {err:.4f}  (Limit: {limit})")
    if err > limit:
        print("[Resolve] → Error too high → clean_error_tracks()")
        clean_error_tracks(context)
    else:
        print("[Resolve] KPI PASS")
    return err


def _weak_frame_exists(context):
    weak = find_first_weak_frame(context)
    print(f"[Resolve] Weak Frame Found: {weak}")
    return bool(weak)


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        scene = context.scene
        clip = getattr(context, "edit_movieclip", None)

        if clip is None:
            print("[Resolve] CANCEL: Kein Clip")
            return {'CANCELLED'}

        max_limit = float(scene.get("max_error_value", 10.0))

        print("\n============== Resolve Start ==============")

        # ==========================================================
        # STAGE 1 — Intrinsics Reset
        # ==========================================================
        print("[Stage1] Reset → cycle_1 → solve")
        refine_intrinsics_reset()
        _cycle_1(context)
        _solve(context)
        err = _kpi_cleanup(context, clip, max_limit)

        if not _weak_frame_exists(context):
            # keine Schwachstelle → weiter
            pass
        else:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            return {'FINISHED'}

        # ==========================================================
        # STAGE 2 — Focal
        # ==========================================================
        print("[Stage2] Focal → solve")
        refine_intrinsics_focal_length_on()
        _solve(context)
        err = _kpi_cleanup(context, clip, max_limit)
        if not _weak_frame_exists(context):
            pass
        else:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            return {'FINISHED'}

        # ==========================================================
        # STAGE 3 — Focal + Principal Point
        # ==========================================================
        print("[Stage3] Focal + Principal → solve")
        refine_intrinsics_principal_point_on()
        _solve(context)
        err = _kpi_cleanup(context, clip, max_limit)
        if not _weak_frame_exists(context):
            pass
        else:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            return {'FINISHED'}

        # ==========================================================
        # STAGE 4 — Volles Paket (inkl. Radial)
        # ==========================================================
        print("[Stage4] Focal + Principal + Radial → solve")
        refine_intrinsics_radial_distortion_on()
        _solve(context)
        err = _kpi_cleanup(context, clip, max_limit)
        if not _weak_frame_exists(context):
            pass
        else:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            return {'FINISHED'}

        print("============== Resolve Finished ==============\n")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
