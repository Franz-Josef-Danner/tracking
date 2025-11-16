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
# interne Helper
# ------------------------------------------------------------
def _solve_camera(context: Context) -> float:
    """Wrapper um solve_camera + Logging; liefert aktuellen Average Error."""
    print("[Resolve] → bpy.ops.clip.solve_camera()")
    bpy.ops.clip.solve_camera()
    avg_error = float(get_average_error())
    print(f"[Resolve] Average Error = {avg_error:.6f}")
    return avg_error


def _get_max_error_value(scene: bpy.types.Scene) -> float:
    """Liest scene.max_error_value, fallback auf 5.0."""
    return float(getattr(scene, "max_error_value", 5.0))


# ------------------------------------------------------------
# Master Resolve Operator
# ------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    bl_idname = "kaiserlich_tracker.master_resolve"
    bl_label = "Master Resolve"
    bl_description = "Master resolve operator for camera tracking"

    # harte Limits als Sicherheitsnetz gegen Endlosschleifen
    MAX_GLOBAL_LOOPS: int = 5
    MAX_STAGE1_LOOPS: int = 3
    MAX_STAGE2_LOOPS: int = 5
    HARD_ERROR_LIMIT: float = 10.0  # dein „> 10 → zurück zu Cycle 1“

    def execute(self, context: Context):
        scene = context.scene

        for global_iter in range(1, self.MAX_GLOBAL_LOOPS + 1):
            print(f"\n============================")
            print(f"[Resolve] GLOBAL LOOP {global_iter}/{self.MAX_GLOBAL_LOOPS}")
            print(f"============================")

            # -------------------------
            # STAGE 1 (Cycle 1)
            # -------------------------
            stage1_state, avg_error = self._run_stage1(context)
            if stage1_state == "MASTER":
                print("[Resolve] Übergabe an Master Cycle aus Stage 1 → DONE")
                return {'FINISHED'}
            if stage1_state == "FAIL":
                print("[Resolve] Stage 1 konnte keinen validen Solve liefern → CANCEL")
                return {'CANCELLED'}

            # wenn wir hier sind: avg_error <= HARD_ERROR_LIMIT
            max_error_value = _get_max_error_value(scene)
            if avg_error <= max_error_value:
                print(f"[Stage1] Error {avg_error:.6f} <= Max {max_error_value:.6f} → DONE")
                return {'FINISHED'}

            # -------------------------
            # STAGE 2 (Cycle 2)
            # -------------------------
            finished, back_to_cycle1 = self._run_stage2(context, avg_error)
            if finished:
                print("[Resolve] Stage 2 beendet → DONE")
                return {'FINISHED'}

            if back_to_cycle1:
                print("[Resolve] Stage 2 fordert Rücksprung zu Stage 1.")
                # global loop → Stage 1 wird erneut gefahren
                continue

        print("[Resolve] MAX_GLOBAL_LOOPS erreicht → CANCEL")
        return {'CANCELLED'}

    # --------------------------------------------------------
    # STAGE 1: reset → solve → ggf. Cleanup → Weak-Frame-Check
    # --------------------------------------------------------
    def _run_stage1(self, context: Context) -> tuple[str, float]:
        """
        Rückgabe:
          ("STAGE2", avg_error)  → Stage 1 fertig, Stage 2 darf übernehmen
          ("MASTER", avg_error)  → an Master-Cycle übergeben
          ("FAIL",   avg_error)  → Abbruch
        """
        print("\n============================")
        print("[Stage1] START")
        print("============================")

        avg_error: float = 0.0

        for i in range(1, self.MAX_STAGE1_LOOPS + 1):
            print(f"[Stage1] Iteration {i}/{self.MAX_STAGE1_LOOPS}")

            # Intrinsics Reset
            print("[Stage1] → refine_intrinsics_reset()")
            refine_intrinsics_reset(context)

            # Cycle 1 start (falls du später einen eigenen Operator einhängst)
            print("[Stage1] → Cycle 1 (aktuell nur Solve)")
            avg_error = _solve_camera(context)

            if avg_error <= self.HARD_ERROR_LIMIT:
                print(f"[Stage1] Average Error {avg_error:.6f} <= {self.HARD_ERROR_LIMIT:.6f} → weiter zu Stage 2")
                return "STAGE2", avg_error

            # Error > 10 → Cleanup und Weak-Frame-Check
            print(f"[Stage1] Average Error {avg_error:.6f} > {self.HARD_ERROR_LIMIT:.6f} → clean_error_tracks()")
            clean_error_tracks(context)

            weak_frame = find_first_weak_frame(context)
            if weak_frame is None:
                # kein Weak Frame → zurück zu Cycle 1 (nächste Iteration)
                print("[Stage1] Kein Weak Frame gefunden → zurück zu Cycle 1")
                continue
            else:
                # Weak Frame gefunden → Übergabe an Master Cycle
                print(f"[Stage1] Weak Frame gefunden ({weak_frame}) → Übergabe an master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return "MASTER", avg_error

        print("[Stage1] MAX_STAGE1_LOOPS erreicht, Error weiterhin zu hoch → FAIL")
        return "FAIL", avg_error

    # --------------------------------------------------------
    # STAGE 2: fokussierte Intrinsics-Eskalation (Cycle 2)
    # --------------------------------------------------------
    def _run_stage2(self, context: Context, avg_error: float) -> tuple[bool, bool]:
        """
        Stage 2 entspricht deinem „Cycle 2 start“ + Eskalationslogik.

        Rückgabe:
          finished=True, back_to_cycle1=False → Resolve fertig (OK oder Übergabe an Master Cycle)
          finished=False, back_to_cycle1=True → Stage 2 möchte zurück zu Cycle 1
        """
        scene = context.scene
        max_error_value = _get_max_error_value(scene)

        print("\n============================")
        print("[Stage2] START (Cycle 2)")
        print("============================")
        print(f"[Stage2] Basis-Error = {avg_error:.6f} (Limit {max_error_value:.6f}, Hard-Limit {self.HARD_ERROR_LIMIT:.6f})")

        # Sicherheitscheck: wenn hier schon ok, sofort raus
        if avg_error <= max_error_value:
            print("[Stage2] Basis-Error bereits <= MaxError → DONE")
            return True, False

        for iteration in range(1, self.MAX_STAGE2_LOOPS + 1):
            print(f"\n[Stage2] Iteration {iteration}/{self.MAX_STAGE2_LOOPS}")

            # ------------------------------------------------
            # STEP 1: refine_intrinsics_focal_length_on
            # ------------------------------------------------
            print("[Stage2][Step1] → refine_intrinsics_focal_length_on() + solve")
            refine_intrinsics_focal_length_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                print(f"[Stage2][Step1] Error {avg_error:.6f} > {self.HARD_ERROR_LIMIT:.6f} → back to Cycle 1")
                return False, True  # zurück zu Stage 1

            if avg_error <= max_error_value:
                print(f"[Stage2][Step1] Error {avg_error:.6f} <= {max_error_value:.6f} → DONE")
                return True, False

            print(f"[Stage2][Step1] Error {avg_error:.6f} > {max_error_value:.6f} → clean_error_tracks()")
            clean_error_tracks(context)

            weak_frame = find_first_weak_frame(context)
            if weak_frame is not None:
                print(f"[Stage2][Step1] Weak Frame {weak_frame} gefunden → Übergabe an master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # ------------------------------------------------
            # STEP 2: focal + principal point
            # ------------------------------------------------
            print("[Stage2][Step2] → refine_intrinsics_focal_length_on + principal_point_on + solve")
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                print(f"[Stage2][Step2] Error {avg_error:.6f} > {self.HARD_ERROR_LIMIT:.6f} → back to Cycle 1")
                return False, True

            if avg_error <= max_error_value:
                print(f"[Stage2][Step2] Error {avg_error:.6f} <= {max_error_value:.6f} → DONE")
                return True, False

            print(f"[Stage2][Step2] Error {avg_error:.6f} > {max_error_value:.6f} → clean_error_tracks()")
            clean_error_tracks(context)

            weak_frame = find_first_weak_frame(context)
            if weak_frame is not None:
                print(f"[Stage2][Step2] Weak Frame {weak_frame} gefunden → Übergabe an master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # ------------------------------------------------
            # STEP 3: focal + principal point + radial distortion
            # ------------------------------------------------
            print("[Stage2][Step3] → refine_intrinsics_focal_length_on + principal_point_on + radial_distortion_on + solve")
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            refine_intrinsics_radial_distortion_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                print(f"[Stage2][Step3] Error {avg_error:.6f} > {self.HARD_ERROR_LIMIT:.6f} → back to Cycle 1")
                return False, True

            if avg_error <= max_error_value:
                print(f"[Stage2][Step3] Error {avg_error:.6f} <= {max_error_value:.6f} → DONE")
                return True, False

            print(f"[Stage2][Step3] Error {avg_error:.6f} > {max_error_value:.6f} → clean_error_tracks()")
            clean_error_tracks(context)

            weak_frame = find_first_weak_frame(context)
            if weak_frame is not None:
                print(f"[Stage2][Step3] Weak Frame {weak_frame} gefunden → Übergabe an master_cycle_operator")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # kein Weak Frame und Error immer noch zu hoch → zurück zu Cycle 2 (nächste Iteration)
            print("[Stage2] Kein Weak Frame, Error weiterhin > MaxError → nächste Iteration Cycle 2")

        print("[Stage2] MAX_STAGE2_LOOPS erreicht → keine weitere Verbesserung")
        # an der Stelle betrachten wir Resolve als „fertig“, obwohl Error hoch ist
        return True, False
