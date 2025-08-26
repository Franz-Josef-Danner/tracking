import bpy
from ..Helper.solve_camera import solve_camera_only


class TrackingCoordinatorOperator(bpy.types.Operator):
    bl_idname = "tracking.coordinator"
    bl_label = "Tracking Coordinator"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    def __init__(self):
        self._state = "INIT"

    def modal(self, context, event):
        if self._state == "SOLVE":
            return self._state_solve(context)
        elif self._state == "SOLVE_WAIT":
            return self._state_solve_wait(context)
        # … weitere States …
        return {"PASS_THROUGH"}

    def _state_solve(self, context):
        """Starte den Kamera-Solve (nur Operator). Danach Wechsel in SOLVE_WAIT."""
        try:
            solve_camera_only(context)
        except Exception as ex:
            print(f"[Coord] SOLVE start failed: {ex!r}")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        self._state = "SOLVE_WAIT"
        return {"RUNNING_MODAL"}

    def _state_solve_wait(self, context):
        """Warte auf Solve-Ergebnis (ggf. Polling/Check ergänzen)."""
        # hier würdest du mit get_current_solve_error(...) oder
        # wait_for_valid_reconstruction(...) arbeiten, wenn gewünscht
        # aktuell nur Übergang in FINALIZE
        self._state = "FINALIZE"
        return {"RUNNING_MODAL"}


# Registrierung
def register():
    bpy.utils.register_class(TrackingCoordinatorOperator)


def unregister():
    bpy.utils.unregister_class(TrackingCoordinatorOperator)


# -----------------------------------------------------------------------------
# PATCH: Operator/tracking_coordinator.py – Solve-Trigger integrieren
# -----------------------------------------------------------------------------
# Unified-Diff zum Einfügen der minimalen Solve-Integration.
#
# 1) Importiere den Minimal-Helper `solve_camera_only`.
# 2) Starte den Solve ausschließlich darüber in `_state_solve`.
# 3) Wechsle anschließend in den Wait-State `SOLVE_WAIT`.
#
# Falls deine Datei andere State-Namen nutzt, passe "SOLVE_WAIT" entsprechend an.

"""
--- a/Operator/tracking_coordinator.py
+++ b/Operator/tracking_coordinator.py
@@
-from ..Helper.solve_camera import (  # ggf. vorhandene alte Imports entfernen/ersetzen
-    # solve_watch_clean,
-)
+from ..Helper.solve_camera import solve_camera_only
@@
 class TrackingCoordinatorOperator(bpy.types.Operator):
@@
-    def _state_solve(self, context):
-        """Solve-Start."""
-        # bisherige Logik hier – ggf. andere Schritte
-        return {'RUNNING_MODAL'}
+    def _state_solve(self, context):
+        """Startet ausschließlich den Kamera-Solve und wechselt in SOLVE_WAIT."""
+        try:
+            res = solve_camera_only(context)  # löst NUR den Operator aus
+            print(f"[Coord] Solve invoked: {res}")
+        except Exception as ex:
+            print(f"[Coord] SOLVE start failed: {ex!r}")
+            # Optional: direkten Abbruch-State wählen
+            if hasattr(self, "_set_state"):
+                try:
+                    self._set_state("FINALIZE")
+                except Exception:
+                    self._state = "FINALIZE"
+            else:
+                self._state = "FINALIZE"
+            return {'RUNNING_MODAL'}
+
+        # In den Wait-State wechseln (passt ggf. an deine FSM an)
+        if hasattr(self, "_set_state"):
+            try:
+                self._set_state("SOLVE_WAIT")
+            except Exception:
+                self._state = "SOLVE_WAIT"
+        else:
+            self._state = "SOLVE_WAIT"
+        return {'RUNNING_MODAL'}
"""
