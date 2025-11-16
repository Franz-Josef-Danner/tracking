# Operator/Master/master_resolve_operator.py
from __future__ import annotations

import bpy
from bpy.types import Operator, Context

# --- Helper-Imports --------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
    from ...Helper.refine_intrinsics import (
        refine_intrinsics_reset,
        refine_intrinsics_focal_length_on,
        refine_intrinsics_principal_point_on,
        refine_intrinsics_radial_distortion_on,
        _get_tracking_settings,  # interne Helper-Funktion gezielt mitbenutzen
    )
    from ...Helper.low_marker_frame import find_first_weak_frame
    from ...Helper.clean_error_tracks import clean_error_tracks
except Exception as e:
    raise ImportError(f"[master_resolve_operator] Missing add-on modules: {e}")


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """
    Kaiserlich Tracker – Resolve Master

    Ablauf (vereinfacht in strukturierte Form gebracht):

        1) Intrinsics-Refine zurücksetzen
        2) cycle_1 (Solve ohne Intrinsics-Refine):
           - Wenn avg_error > 10:
                clean_error_tracks
                wenn KEIN weak_frame → cycle_1 erneut
                sonst → Übergabe an master_cycle_operator
           - Wenn avg_error <= 10:
                weiter zu cycle_2

        3) cycle_2 (stufige Intrinsics-Eskalation):
           - Start: Prüfe avg_error gegen scene.max_error_value
           - Stufe 1: Refine Focal
           - Stufe 2: Refine Focal + Principal
           - Stufe 3: Refine Focal + Principal + Radial
           - Nach jeder Stufe:
                * solve_camera
                * wenn avg_error <= max_error_value → FINISHED
                * sonst clean_error_tracks + weak_frame-Check
                    - wenn weak_frame vorhanden → Übergabe an master_cycle_operator
                    - wenn kein weak_frame → nächste Stufe
           - Wenn nach Stufe 3 immer noch > max_error_value und kein weak_frame:
                optionaler einmaliger Wiederholungsdurchlauf cycle_2;
                danach fallback → master_cycle_operator

    Wichtige Konvention:
        - weak_frame == None → "kein schwacher Frame" (kein Unterdeckungspunkt)
        - weak_frame != None → Übergabe an master_cycle_operator
    """
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------ #
    # Public API: execute
    # ------------------------------------------------------------------ #
    def execute(self, context: Context):
        scene = context.scene
        max_err_scene = float(getattr(scene, "max_error_value", 2.0))

        print("\n[Resolve] ================== START ==================")
        print(f"[Resolve] scene.max_error_value = {max_err_scene}")

        # 0) Intrinsics-Refine komplett zurücksetzen
        if not refine_intrinsics_reset():
            print("[Resolve] WARNUNG: refine_intrinsics_reset() konnte Tracking-Settings nicht finden.")

        # 1) cycle_1 – Basis-Solve ohne Intrinsics-Refine
        self._cycle_1(context)

        avg_err = float(get_average_error())
        print(f"[Resolve] Nach cycle_1: average_error = {avg_err:.4f}")

        if avg_err > 10.0:
            # Schlechtes Global-Niveau → Cleaning + Weak-Frame-Check
            print("[Resolve] average_error > 10 → clean_error_tracks + weak_frame-Check (Phase 1)")
            clean_error_tracks(context)
            weak = find_first_weak_frame(context)

            if weak is None:
                # Kein schwacher Frame → cycle_1 noch einmal probieren
                print("[Resolve] Kein weak_frame gefunden → cycle_1 erneut ausführen")
                self._cycle_1(context)
                avg_err = float(get_average_error())
                print(f"[Resolve] Nach zweitem cycle_1: average_error = {avg_err:.4f}")

                if avg_err > 10.0:
                    # Immer noch schlecht → Übergabe an Master Cycle
                    print("[Resolve] average_error weiterhin > 10 → Übergabe an master_cycle_operator")
                    self._call_master_cycle(context)
                    print("[Resolve] ================== ENDE (delegiert) ==================")
                    return {'FINISHED'}
                else:
                    # Jetzt brauchbares Niveau → direkt in cycle_2
                    print("[Resolve] average_error <= 10 nach zweitem cycle_1 → weiter zu cycle_2")
                    finished = self._cycle_2(context, max_err_scene, depth=0)
                    print("[Resolve] ================== ENDE (cycle_2) ==================")
                    return {'FINISHED'}
            else:
                # Schwacher Frame → Master Cycle übernimmt
                print(f"[Resolve] weak_frame gefunden bei Frame {weak} → Übergabe an master_cycle_operator")
                self._call_master_cycle(context)
                print("[Resolve] ================== ENDE (delegiert) ==================")
                return {'FINISHED'}

        else:
            # avg_error <= 10 → direkt cycle_2 (Feintuning)
            print("[Resolve] average_error <= 10 → direkt zu cycle_2")
            finished = self._cycle_2(context, max_err_scene, depth=0)
            print("[Resolve] ================== ENDE (cycle_2) ==================")
            return {'FINISHED'}

    # ------------------------------------------------------------------ #
    # Interne Hilfsfunktionen
    # ------------------------------------------------------------------ #

    def _solve_camera(self, context: Context) -> bool:
        """
        Führt Blenders solve_camera-Operator aus.
        Achtung: Erfordert im Normalfall gültigen CLIP_EDITOR-Kontext.
        """
        try:
            print("[Resolve] -> bpy.ops.clip.solve_camera()")
            result = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            print(f"[Resolve] solve_camera Result: {result}")
            return 'FINISHED' in result
        except Exception as e:
            print(f"[Resolve] FEHLER in solve_camera: {e}")
            return False

    def _set_intrinsics_combo(self, focal: bool, principal: bool, radial: bool) -> None:
        """
        Setzt beliebige Kombinationen von refine_intrinsics_*.
        Nutzt bewusst _get_tracking_settings aus Helper/refine_intrinsics.py,
        da die öffentlichen Funktionen jeweils exklusiv schalten.
        """
        try:
            settings = _get_tracking_settings(None)
        except Exception:
            settings = None

        if not settings:
            print("[Resolve] WARNUNG: _set_intrinsics_combo: Keine TrackingSettings gefunden.")
            return

        settings.refine_intrinsics_focal_length = focal
        settings.refine_intrinsics_principal_point = principal
        settings.refine_intrinsics_radial_distortion = radial

        print(
            "[Resolve] refine_intrinsics-Combo gesetzt: "
            f"focal={focal}, principal={principal}, radial={radial}"
        )

    # ------------------------------------------------------------------ #
    # CYCLE 1
    # ------------------------------------------------------------------ #
    def _cycle_1(self, context: Context) -> None:
        """
        cycle_1:
          - Intrinsics auf OFF
          - solve_camera einmalig
        """
        print("\n[Resolve][cycle_1] -----------------------------------")
        # Sicherheitshalber nochmal resetten, um Garantien zu haben
        refine_intrinsics_reset()
        self._set_intrinsics_combo(False, False, False)
        self._solve_camera(context)
        avg = float(get_average_error())
        print(f"[Resolve][cycle_1] average_error nach Solve: {avg:.4f}")

    # ------------------------------------------------------------------ #
    # CYCLE 2 – Intrinsics-Eskalation
    # ------------------------------------------------------------------ #
    def _cycle_2(self, context: Context, max_err_scene: float, depth: int = 0) -> bool:
        """
        cycle_2 – stufige Intrinsics-Eskalation.

        Rückgabe:
            True  -> Ablauf in cycle_2 abgeschlossen (Fehler <= max_err_scene oder
                    Stufen-Logik endet regulär)
            False -> Kontrolle wurde an master_cycle_operator delegiert
        """
        print(f"\n[Resolve][cycle_2] ===== START (depth={depth}) =====")
        if depth > 1:
            # Sicherheitsnetz gegen unendliche Rekursion
            print("[Resolve][cycle_2] depth-Limit erreicht → Übergabe an master_cycle_operator")
            self._call_master_cycle(context)
            return False

        err_start = float(get_average_error())
        print(f"[Resolve][cycle_2] Start average_error = {err_start:.4f}")

        if err_start <= max_err_scene:
            print("[Resolve][cycle_2] Fehler bereits <= scene.max_error_value → FINISHED")
            return True

        # --- Stufe 1: Refine Focal ------------------------------------
        print("[Resolve][cycle_2] Stufe 1: Refine Focal")
        self._set_intrinsics_combo(True, False, False)
        self._solve_camera(context)
        if self._check_after_stage(context, max_err_scene, stage_name="Focal"):
            return True

        # --- Stufe 2: Refine Focal + Principal ------------------------
        print("[Resolve][cycle_2] Stufe 2: Refine Focal + Principal")
        self._set_intrinsics_combo(True, True, False)
        self._solve_camera(context)
        if self._check_after_stage(context, max_err_scene, stage_name="Focal+Principal"):
            return True

        # --- Stufe 3: Refine Focal + Principal + Radial ---------------
        print("[Resolve][cycle_2] Stufe 3: Refine Focal + Principal + Radial")
        self._set_intrinsics_combo(True, True, True)
        self._solve_camera(context)
        if self._check_after_stage(context, max_err_scene, stage_name="Focal+Principal+Radial"):
            return True

        # Wenn wir hier sind: Nach Stufe 3 immer noch > max_err_scene,
        # kein weak_frame in den Zwischenprüfungen → optionaler zweiter Durchlauf.
        err_final = float(get_average_error())
        print(
            "[Resolve][cycle_2] Nach voller Intrinsics-Eskalation noch zu hoher Fehler: "
            f"{err_final:.4f} > {max_err_scene:.4f}"
        )
        print("[Resolve][cycle_2] Versuche einmaligen zweiten Durchlauf (depth+1).")
        return self._cycle_2(context, max_err_scene, depth=depth + 1)

    def _check_after_stage(self, context: Context, max_err_scene: float, stage_name: str) -> bool:
        """
        Gemeinsame Logik nach jeder Intrinsics-Stufe:

            - Fehler prüfen
            - Falls > max_err_scene:
                * clean_error_tracks
                * weak_frame-Check
                    - weak_frame != None → Übergabe an master_cycle_operator
                    - weak_frame == None → weiter zur nächsten Stufe
        """
        avg_err = float(get_average_error())
        print(f"[Resolve][cycle_2][{stage_name}] average_error = {avg_err:.4f}")

        if avg_err <= max_err_scene:
            print(f"[Resolve][cycle_2][{stage_name}] Fehler <= max_err_scene → FINISHED")
            return True

        print(f"[Resolve][cycle_2][{stage_name}] Fehler > max_err_scene → clean_error_tracks + weak_frame-Check")
        clean_error_tracks(context)
        weak = find_first_weak_frame(context)

        if weak is not None:
            print(
                f"[Resolve][cycle_2][{stage_name}] weak_frame gefunden bei Frame {weak} "
                "→ Übergabe an master_cycle_operator"
            )
            self._call_master_cycle(context)
            return False

        print(f"[Resolve][cycle_2][{stage_name}] Kein weak_frame → weiter zur nächsten Stufe")
        return False

    # ------------------------------------------------------------------ #
    # Übergabe an Master Cycle
    # ------------------------------------------------------------------ #
    def _call_master_cycle(self, context: Context) -> None:
        """
        Wrapper für den Aufruf des Master-Cycle-Operators.
        """
        try:
            print("[Resolve] -> bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')")
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
        except Exception as e:
            print(f"[Resolve] FEHLER beim Aufruf von master_cycle_operator: {e}")
