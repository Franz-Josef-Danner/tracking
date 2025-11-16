# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator, Context

# Helper Imports
from ...Helper.refine_intrinsics import (
    refine_intrinsics_reset,
)
from ...Helper.get_average_error import get_average_error


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Minimalistische Resolve-Pipeline:
    1) Reset Intrinsics
    2) Master-Cycle
    3) Solve Camera
    """
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):

        clip = getattr(context, "edit_movieclip", None)
        if not clip:
            print("[Resolve] Kein Clip → CANCEL")
            return {'CANCELLED'}

        print("[Resolve] Starte Resolve-Pipeline")

        # STEP 1: Intrinsics Reset
        print("[Resolve] Step 1 → refine_intrinsics_reset()")
        refine_intrinsics_reset()

        # STEP 2: Master Cycle
        print("[Resolve] Step 2 → Master Cycle")
        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('EXEC_DEFAULT')
        except Exception as e:
            print(f"[Resolve] Fehler MasterCycle: {e}")

        # STEP 3: Solve Camera
        print("[Resolve] Step 3 → Solve Camera")
        try:
            bpy.ops.clip.solve_camera()
        except Exception as e:
            print(f"[Resolve] SolveCamera Fehler: {e}")

        # KPI
        err = get_average_error(clip)
        print(f"[Resolve] Final Average Error = {err:.4f}")

        print("[Resolve] Pipeline → FINISHED")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
