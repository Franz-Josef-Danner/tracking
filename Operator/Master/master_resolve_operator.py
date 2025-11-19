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
from ...Helper.low_marker_frame_solve import find_first_weak_frame_solve


# ------------------------------------------------------------
# interne Helper
# ------------------------------------------------------------
def _solve_camera(context: Context) -> float:
    """Wrapper um solve_camera + Logging; liefert aktuellen Average Error."""
    bpy.ops.clip.solve_camera()
    try:
        avg_error = float(get_average_error())
    except Exception:
        # Nicht konvertierbar → wie > HARD_LIMIT behandeln
        return float('inf')

    # NaN oder zu kleines/negatives Chaos? → als unlösbar behandeln
    if avg_error != avg_error or avg_error < 0:
        print("[Resolve] Invalid avg error detected (NaN/Negative). Forcing fallback > HARD_LIMIT.")
        return float('inf')

    return avg_error


def _get_max_error_value(scene: bpy.types.Scene) -> float:
    """Liest scene.max_error_value, fallback auf 5.0."""
    return float(getattr(scene, "max_error_value", 5.0))


# ------------------------------------------------------------
# Master Resolve Operator
# ------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
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

            stage1_state, avg_error = self._run_stage1(context)
            if stage1_state == "MASTER":
                return {'FINISHED'}
            if stage1_state == "FAIL":
                return {'CANCELLED'}

            # wenn wir hier sind: avg_error <= HARD_ERROR_LIMIT
            max_error_value = _get_max_error_value(scene)
            if avg_error <= max_error_value:
                return {'FINISHED'}

            # -------------------------
            # STAGE 2 (Cycle 2)
            # -------------------------
            finished, back_to_cycle1 = self._run_stage2(context, avg_error)
            if finished:
                return {'FINISHED'}

            if back_to_cycle1:
                # global loop → Stage 1 wird erneut gefahren
                continue

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
        

        avg_error: float = 0.0

        for i in range(1, self.MAX_STAGE1_LOOPS + 1):

            # Intrinsics Reset
            refine_intrinsics_reset(context)

            # Cycle 1 start (falls du später einen eigenen Operator einhängst)
            avg_error = _solve_camera(context)

            if avg_error <= self.HARD_ERROR_LIMIT:
                return "STAGE2", avg_error

            # Error > 10 → Cleanup und Weak-Frame-Check
            clean_error_tracks(context)

            weak_frame = find_first_weak_frame_solve(context)
            if weak_frame is None:
                # kein Weak Frame → zurück zu Cycle 1 (nächste Iteration)
                continue
            else:
                # Weak Frame gefunden → Übergabe an Master Cycle
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return "MASTER", avg_error

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


        # Sicherheitscheck: wenn hier schon ok, sofort raus
        if avg_error <= max_error_value:
            return True, False

        for iteration in range(1, self.MAX_STAGE2_LOOPS + 1):

            # ------------------------------------------------
            # STEP 1: refine_intrinsics_focal_length_on
            # ------------------------------------------------
            refine_intrinsics_focal_length_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                return False, True  # zurück zu Stage 1

            if avg_error <= max_error_value:
                return True, False

            clean_error_tracks(context)

            weak_frame = find_first_weak_frame_solve(context)
            if weak_frame is not None:
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # ------------------------------------------------
            # STEP 2: focal + principal point
            # ------------------------------------------------
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                return False, True

            if avg_error <= max_error_value:
                return True, False

            clean_error_tracks(context)

            weak_frame = find_first_weak_frame_solve(context)
            if weak_frame is not None:
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # ------------------------------------------------
            # STEP 3: focal + principal point + radial distortion
            # ------------------------------------------------
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            refine_intrinsics_radial_distortion_on(context)
            avg_error = _solve_camera(context)

            if avg_error > self.HARD_ERROR_LIMIT:
                return False, True

            if avg_error <= max_error_value:
                return True, False

            clean_error_tracks(context)

            weak_frame = find_first_weak_frame_solve(context)
            if weak_frame is not None:
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                return True, False

            # kein Weak Frame und Error immer noch zu hoch → zurück zu Cycle 2 (nächste Iteration)

        # an der Stelle betrachten wir Resolve als „fertig“, obwohl Error hoch ist
        return True, False
