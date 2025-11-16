# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator, Context

# ------------------------------------------------------------
# Helper Imports
# ------------------------------------------------------------
from ...Helper.refine_intrinsics import refine_intrinsics_reset
from ...Helper.get_average_error import get_average_error
from ...Helper.clean_error_tracks import clean_error_tracks


# ------------------------------------------------------------
# Platzhalter-Funktion für Cycle_1
# Hier bitte deinen echten Pipeline-Ablauf einsetzen
# ------------------------------------------------------------
def run_cycle_1(context: Context):
    """
    Führt den initialen Tracking-Cycle aus.
    TODO: durch echten Operator-Aufruf ersetzen
    z.B.: bpy.ops.kaiserlich_tracker.master_cycle_operator()
    """
    print("[Resolve] (Mock) cycle_1 → NO REAL IMPLEMENTATION")
    return True


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """
    Resolve-Master-Pipeline:
    1) Intrinsics reset
    2) cycle_1
    3) solve camera
    4) KPI-Gate → clean_error_tracks bei schlechtem Ergebnis
    """
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    MAX_ACCEPTABLE_ERROR: float = 10.0

    def execute(self, context: Context):

        clip = getattr(context, "edit_movieclip", None)
        if clip is None:
            print("[Resolve] CANCEL: Kein aktiver Clip")
            return {'CANCELLED'}

        print("\n============================")
        print("  KAISERLICH RESOLVE START")
        print("============================")

        # --------------------------------------------------------
        # Step 1 — Intrinsics Reset
        # --------------------------------------------------------
        print("[Resolve] Step 1 → refine_intrinsics_reset()")
        try:
            refine_intrinsics_reset()
        except Exception as e:
            print(f"[Resolve] ERROR refine_intrinsics_reset: {e}")

        # --------------------------------------------------------
        # Step 2 — Cycle_1
        # --------------------------------------------------------
        print("[Resolve] Step 2 → cycle_1()")
        try:
            run_cycle_1(context)
        except Exception as e:
            print(f"[Resolve] ERROR cycle_1: {e}")

        # --------------------------------------------------------
        # Step 3 — Solve Camera
        # --------------------------------------------------------
        print("[Resolve] Step 3 → bpy.ops.clip.solve_camera()")
        try:
            bpy.ops.clip.solve_camera()
        except Exception as e:
            print(f"[Resolve] ERROR solve_camera: {e}")

        # --------------------------------------------------------
        # Step 4 — KPI & Cleanup
        # --------------------------------------------------------
        err = get_average_error(clip)
        print(f"[Resolve] Average Error = {err:.4f}")

        if err > self.MAX_ACCEPTABLE_ERROR:
            print(f"[Resolve] KPI FAIL  Error {err:.4f} > {self.MAX_ACCEPTABLE_ERROR}")
            print("[Resolve] Cleanup: clean_error_tracks()")
            try:
                removed = clean_error_tracks(context)
                print(f"[Resolve] Cleanup removed {removed} tracks")
            except Exception as e:
                print(f"[Resolve] ERROR clean_error_tracks: {e}")
        else:
            print("[Resolve] KPI PASS  → No Cleanup")

        print("============================")
        print("  KAISERLICH RESOLVE DONE")
        print("============================\n")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
