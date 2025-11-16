from __future__ import annotations
import bpy
from bpy.types import Operator, Context

# ------------------------------------------------------------
# Helper Imports
# ------------------------------------------------------------
from ...Helper.refine_intrinsics import (
    refine_intrinsics_reset,
    refine_intrinsics_focal_length_on,
    refine_intrinsics_principal_point_on,
    refine_intrinsics_radial_distortion_on,
)
from ...Helper.get_average_error import get_average_error
from ...Helper.clean_error_tracks import clean_error_tracks
from ...Helper.low_marker_frame import find_first_weak_frame


# ------------------------------------------------------------
# Platzhalter für deine Zyklen
# → HIER deine echten Operator-Aufrufe einsetzen
# ------------------------------------------------------------
def run_cycle_1(context: Context) -> None:
    """
    cycle_1 start:
    Hier einen Tracking-/Cleanup-Cycle starten, NICHT den Resolve selbst.
    Beispiel:
        bpy.ops.kaiserlich_tracker.master_track_operator('INVOKE_DEFAULT')
    """
    print("[Resolve] cycle_1 start (TODO: echten Operator einhängen)")


def run_cycle_2(context: Context) -> None:
    """
    cycle_2 start:
    Zweiter, ggf. aggressiverer Cycle.
    Beispiel:
        bpy.ops.kaiserlich_tracker.master_track_operator_backwards('INVOKE_DEFAULT')
    """
    print("[Resolve] cycle_2 start (TODO: echten Operator einhängen)")


# ------------------------------------------------------------
# Interne Helper
# ------------------------------------------------------------
def _solve_camera(context: Context) -> None:
    print("[Resolve] → bpy.ops.clip.solve_camera()")
    bpy.ops.clip.solve_camera()


def _get_err(clip) -> float:
    try:
        return float(get_average_error(clip))
    except Exception as e:
        print(f"[Resolve] ERROR get_average_error: {e}")
        return 0.0


def _has_weak_frame(context: Context) -> bool:
    weak = find_first_weak_frame(context)
    print(f"[Resolve] find_first_weak_frame → {weak}")
    return bool(weak)


def _cleanup_if_needed(context: Context, clip, limit: float, label: str) -> float:
    err = _get_err(clip)
    print(f"[Resolve][{label}] Average Error = {err:.6f} (Limit {limit:.6f})")
    if err > limit:
        print(f"[Resolve][{label}] Error {err:.6f} > {limit:.6f} → clean_error_tracks()")
        try:
            removed = clean_error_tracks(context)
            print(f"[Resolve][{label}] clean_error_tracks removed: {removed}")
        except Exception as e:
            print(f"[Resolve][{label}] ERROR clean_error_tracks: {e}")
    else:
        print(f"[Resolve][{label}] Error OK → kein Cleanup")
    return err


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """
    Mehrstufige Resolve-Pipeline gemäß Vorgabe:

    STAGE 1:
        refine_intrinsics_reset
        cycle_1 start
        solve_camera
        if err > 10:
            clean_error_tracks
            if kein weak frame:
                → zurück zu cycle_1 (Loop)
            else:
                → master_cycle_operator + Finish
        else:
            → STAGE 2

    STAGE 2 (cycle_2, mit scene.max_error_value):
        cycle_2 start
        if err > max_err:
            1) focal on → solve → ggf. cleanup
               if weak frame: → master_cycle_operator
            2) focal + principal → solve → ggf. cleanup
               if weak frame: → master_cycle_operator
            3) focal + principal + radial → solve → ggf. cleanup
               if weak frame: → master_cycle_operator
               else (kein weak frame):
                   → zurück zu cycle_2 (Loop, begrenzt)
        else:
            finished
    """
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    # Sicherheitsgrenzen gegen Endlosschleifen
    MAX_STAGE1_LOOPS: int = 5
    MAX_STAGE2_LOOPS: int = 5

    def execute(self, context: Context):

        clip = getattr(context, "edit_movieclip", None) or getattr(context.scene, "movieclip", None)
        if clip is None:
            print("[Resolve] CANCEL: Kein aktiver Clip")
            return {'CANCELLED'}

        scene = context.scene
        stage2_limit = float(getattr(scene, "max_error_value", 10.0))
        stage1_limit = 10.0  # wie von dir vorgegeben

        print("\n============================")
        print("  KAISERLICH RESOLVE START")
        print("============================")

        # --------------------------------------------------------
        # STAGE 1 – reset + cycle_1-loop
        # --------------------------------------------------------
        stage1_iter = 0
        while True:
            stage1_iter += 1
            print(f"\n[Stage1] Iteration {stage1_iter}/{self.MAX_STAGE1_LOOPS}")

            print("[Stage1] → refine_intrinsics_reset()")
            try:
                refine_intrinsics_reset()
            except Exception as e:
                print(f"[Stage1] ERROR refine_intrinsics_reset: {e}")

            print("[Stage1] → cycle_1 start")
            run_cycle_1(context)

            print("[Stage1] → solve_camera()")
            _solve_camera(context)

            # Error prüfen und ggf. Cleanup
            err = _cleanup_if_needed(context, clip, stage1_limit, "Stage1")

            if err > stage1_limit:
                # Schlecht → Weak Frame prüfen
                if not _has_weak_frame(context):
                    print("[Stage1] Kein weak frame → zurück zu cycle_1 (Loop)")
                    if stage1_iter >= self.MAX_STAGE1_LOOPS:
                        print("[Stage1] MAX_STAGE1_LOOPS erreicht → Breche STAGE 1 ab, gehe zu STAGE 2")
                        break
                    continue  # zurück zum Anfang von STAGE 1
                else:
                    print("[Stage1] Weak Frame gefunden → Übergabe an master_cycle_operator")
                    bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                    print("============================")
                    print("  KAISERLICH RESOLVE DONE")
                    print("============================\n")
                    return {'FINISHED'}
            else:
                # Error <= 10 → STAGE 2
                print("[Stage1] Error <= 10 → Wechsel zu STAGE 2")
                break

        # --------------------------------------------------------
        # STAGE 2 – cycle_2 + Eskalation Intrinsics
        # --------------------------------------------------------
        stage2_iter = 0
        while True:
            stage2_iter += 1
            print(f"\n[Stage2] Iteration {stage2_iter}/{self.MAX_STAGE2_LOOPS}")
            print("[Stage2] → cycle_2 start")
            run_cycle_2(context)

            # Basis-Error nach cycle_2
            base_err = _get_err(clip)
            print(f"[Stage2] Basis-Error nach cycle_2 = {base_err:.6f} (Limit {stage2_limit:.6f})")

            if base_err <= stage2_limit:
                print("[Stage2] Basis-Error <= Limit → Finished.")
                print("============================")
                print("  KAISERLICH RESOLVE DONE")
                print("============================\n")
                return {'FINISHED'}

            # ----------------------------------------------------
            # Step 1 – focal on
            # ----------------------------------------------------
            print("[Stage2][Step1] → refine_intrinsics_focal_length_on() + solve")
            try:
                refine_intrinsics_focal_length_on()
            except Exception as e:
                print(f"[Stage2][Step1] ERROR refine_intrinsics_focal_length_on: {e}")

            _solve_camera(context)
            err = _cleanup_if_needed(context, clip, stage2_limit, "Stage2-Step1")

            if _has_weak_frame(context):
                print("[Stage2][Step1] Weak Frame gefunden → master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                print("============================")
                print("  KAISERLICH RESOLVE DONE")
                print("============================\n")
                return {'FINISHED'}

            # ----------------------------------------------------
            # Step 2 – focal + principal
            # ----------------------------------------------------
            print("[Stage2][Step2] → refine_intrinsics_focal_length_on + principal_point_on + solve")
            try:
                refine_intrinsics_focal_length_on()
                refine_intrinsics_principal_point_on()
            except Exception as e:
                print(f"[Stage2][Step2] ERROR refine_intrinsics_*: {e}")

            _solve_camera(context)
            err = _cleanup_if_needed(context, clip, stage2_limit, "Stage2-Step2")

            if _has_weak_frame(context):
                print("[Stage2][Step2] Weak Frame gefunden → master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                print("============================")
                print("  KAISERLICH RESOLVE DONE")
                print("============================\n")
                return {'FINISHED'}

            # ----------------------------------------------------
            # Step 3 – focal + principal + radial
            # ----------------------------------------------------
            print("[Stage2][Step3] → refine_intrinsics_focal + principal + radial + solve")
            try:
                refine_intrinsics_focal_length_on()
                refine_intrinsics_principal_point_on()
                refine_intrinsics_radial_distortion_on()
            except Exception as e:
                print(f"[Stage2][Step3] ERROR refine_intrinsics_*: {e}")

            _solve_camera(context)
            err = _cleanup_if_needed(context, clip, stage2_limit, "Stage2-Step3")

            if _has_weak_frame(context):
                print("[Stage2][Step3] Weak Frame gefunden → master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                print("============================")
                print("  KAISERLICH RESOLVE DONE")
                print("============================\n")
                return {'FINISHED'}

            # → Kein weak frame in allen drei Stufen
            print("[Stage2] Kein weak frame in allen Steps → zurück zu cycle_2 (Loop)")

            if stage2_iter >= self.MAX_STAGE2_LOOPS:
                print("[Stage2] MAX_STAGE2_LOOPS erreicht → harter Finish ohne Übergabe")
                print("============================")
                print("  KAISERLICH RESOLVE DONE")
                print("============================\n")
                return {'FINISHED'}
            # sonst: while-Schleife wiederholt cycle_2

    # --------------------------------------------------------
    # Register/Unregister
    # --------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
