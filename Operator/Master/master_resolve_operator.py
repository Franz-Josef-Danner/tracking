# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator, Context

from ...Helper.get_average_error import get_average_error
from ...Helper.refine_intrinsics import (
    refine_intrinsics_reset,
    refine_intrinsics_focal_length_on,
    refine_intrinsics_principal_point_on,
    refine_intrinsics_radial_distortion_on,
)
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.clean_error_tracks import clean_error_tracks


def _solve_camera(context: Context) -> None:
    try:
        bpy.ops.clip.solve_camera()
    except Exception as e:
        print(f"[Resolve] Solve Fehler: {e}")


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Deterministische Intrinsics-Resolve Pipeline gemäß neuer Vorgaben"""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        scene = context.scene
        clip = getattr(context, "edit_movieclip", None)

        if not clip:
            print("[Resolve] Kein Clip → CANCEL")
            return {'CANCELLED'}

        max_err = float(scene.get("max_error_value", 10.0))
        print(f"[Resolve] Starte Resolve-Prozess (max_error_value={max_err})")

        # ==================================================================
        # CYCLE 1
        # ==================================================================
        print("\n[Resolve] === CYCLE 1 ===")
        refine_intrinsics_reset()
        _solve_camera(context)

        err = get_average_error(clip)
        print(f"[Resolve][Cycle1] Average Error = {err:.3f}")

        if err > 10.0:
            print("[Resolve][Cycle1] Hoher Fehler → Clean Error Tracks")
            clean_error_tracks(context)

            frame = find_first_weak_frame(context)
            if frame is None:
                print("[Resolve][Cycle1] Kein weak frame → zurück zu Cycle1")
                return bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
            else:
                print(f"[Resolve][Cycle1] Weak Frame gefunden → Übergabe an MasterCycle")
                return bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')

        # ==================================================================
        # CYCLE 2 (Eskalationsstufen)
        # ==================================================================
        print("\n[Resolve] === CYCLE 2 ===")

        def cycle2_step(step_name: str, refine_fn):
            print(f"[Resolve][Cycle2] Step: {step_name}")
            refine_fn()
            _solve_camera(context)

            err = get_average_error(clip)
            print(f"[Resolve][{step_name}] Average Error = {err:.3f}")

            if err > max_err:
                print(f"[Resolve][{step_name}] Fehler > {max_err} → Clean")
                clean_error_tracks(context)

            frame = find_first_weak_frame(context)
            if frame is None:
                print(f"[Resolve][{step_name}] Kein Weak Frame → weiter eskalieren")
                return False  # weiter
            else:
                print(f"[Resolve][{step_name}] Weak Frame {frame} gefunden → MasterCycle")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True  # break

        # Step A: Focal only
        if cycle2_step("FocalOnly", refine_intrinsics_focal_length_on):
            return {'FINISHED'}

        # Step B: Focal + PP
        def refine_fp():
            refine_intrinsics_focal_length_on()
            refine_intrinsics_principal_point_on()

        if cycle2_step("Focal+Principal", refine_fp):
            return {'FINISHED'}

        # Step C: Focal + PP + Radial
        def refine_fpr():
            refine_intrinsics_focal_length_on()
            refine_intrinsics_principal_point_on()
            refine_intrinsics_radial_distortion_on()

        if cycle2_step("Focal+Principal+Radial", refine_fpr):
            return {'FINISHED'}

        # ==================================================================
        # Wenn kein Weak-Frame nach kompletter Eskalation → zurück zu Cycle2
        # ==================================================================
        print("[Resolve][Cycle2] Kein Erfolg → erneute Cycle2-Iteration")
        return bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
