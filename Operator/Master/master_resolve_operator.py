# master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator
import io
import contextlib

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
    """
    Kaiserlich Tracker – Resolve Master (modal)

    Ablauf:

    Stage 0:
        - Intrinsics reset
        - Solve
        - Wenn avg_error > 10:
            - clean_error_tracks
            - weak_frame:
                - None  -> FINISHED
                - sonst -> MasterCycle (INVOKE_DEFAULT) und FINISHED
        - Wenn avg_error <= 10:
            - weiter zu Stage 1

    Stage 1 (Focal):
        - Intrinsics reset
        - refine_intrinsics_focal_length_on
        - Solve
        - Wenn avg_error <= max_error_value: FINISHED
        - Wenn avg_error > max_error_value:
            - clean_error_tracks
            - weak_frame:
                - None  -> Stage 2
                - sonst -> MasterCycle (INVOKE_DEFAULT) und FINISHED

    Stage 2 (Focal + Principal):
        - Intrinsics reset
        - refine_intrinsics_focal_length_on
        - refine_intrinsics_principal_point_on
        - Solve
        - Wenn avg_error <= max_error_value: FINISHED
        - Wenn avg_error > max_error_value:
            - clean_error_tracks
            - weak_frame:
                - None  -> Stage 3
                - sonst -> MasterCycle (INVOKE_DEFAULT) und FINISHED

    Stage 3 (Focal + Principal + Radial):
        - Intrinsics reset
        - refine_intrinsics_focal_length_on
        - refine_intrinsics_principal_point_on
        - refine_intrinsics_radial_distortion_on
        - Solve
        - Wenn avg_error <= max_error_value: FINISHED
        - Wenn avg_error > max_error_value:
            - clean_error_tracks
            - weak_frame:
                - None  -> FINISHED
                - sonst -> MasterCycle (INVOKE_DEFAULT) und FINISHED
    """

    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (staged)"
    bl_description = (
        "Führt den Kamera-Solve in bis zu vier gestaffelten Stufen aus, "
        "nutzt Error-Grenzwerte und Weak-Frame-Check, und übergibt bei Bedarf an den Master Cycle."
    )
    bl_options = {'REGISTER', 'UNDO'}

    # Modal-Parameter
    poll_interval: bpy.props.FloatProperty(default=0.25)
    timeout_seconds: bpy.props.FloatProperty(default=8.0)

    # interner Zustand
    _timer = None
    _phase = 0
    _stage = 0       # 0,1,2,3
    _elapsed = 0.0
    _avg_error = None
    _area = _region = _space = None
    _subphase = 0  # 0 = Solve, 1 = Evaluate/Decide

    # ---------------- Lifecycle ----------------
    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 0
        self._stage = 0
        self._elapsed = 0.0
        self._avg_error = None
        self._subphase = 0
        self._update_progress(context, 0)
        print("\n[Resolve] Invoke gestartet – initialisiere Resolve-Pipeline.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # PHASE 0: Clip-Editor-Kontext suchen
        if self._phase == 0:
            print("\n[Resolve][Phase 0] Suche nach Clip-Editor-Kontext ...")
            self._area, self._region, self._space = self._find_clip_context()
            if not (self._space and getattr(self._space, "clip", None)):
                print("[Resolve][Phase 0] Kein Clip-Editor mit aktivem Clip gefunden → Abbruch.")
                return self._finish(context, cancelled=True)
            print("[Resolve][Phase 0] Clip-Editor gefunden → Wechsel zu Phase 1 (Stages).")
            self._phase = 1
            self._stage = 0
            self._update_progress(context, 0)
            return {'RUNNING_MODAL'}

        # PHASE 1: Stages 0–3 sequentiell
        if self._phase == 1:
            # --- Subphase 0: Solve ---
            if self._subphase == 0:
                if not self._run_solve_only(context, self._stage):
                    print(f"[Resolve][Stage {self._stage}] Solve fehlgeschlagen → ABORT.")
                    return self._finish(context, cancelled=True)
                self._subphase = 1
                return {'RUNNING_MODAL'}

            # --- Subphase 1: Evaluate + Decision ---
            if self._subphase == 1:
                if self._stage == 0:
                    decision, next_stage = self._run_stage0_evaluate(context)
                elif self._stage == 1:
                    decision, next_stage = self._run_stage1_evaluate(context)
                elif self._stage == 2:
                    decision, next_stage = self._run_stage2_evaluate(context)
                elif self._stage == 3:
                    decision, next_stage = self._run_stage3_evaluate(context)
                else:
                    print(f"[Resolve] Ungültige Stage {self._stage} → Abbruch.")
                    return self._finish(context, cancelled=True)

            # Entscheidung auswerten
            if decision == "NEXT_STAGE":
                self._stage = next_stage
                self._subphase = 0
                progress = int((self._stage / 3) * 100) if self._stage > 0 else 0
                self._update_progress(context, progress)
                print(f"[Resolve] Wechsel zu Stage {self._stage} (Progress: {progress} %).")
                return {'RUNNING_MODAL'}

            elif decision == "MASTER_CYCLE":
                print("[Resolve] Übergabe an MasterCycle-Operator (INVOKE_DEFAULT).")
                try:
                    bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                except Exception as e:
                    print(f"[Resolve] FEHLER beim Aufruf von master_cycle_operator: {e}")
                self._update_progress(context, 100)
                self._subphase = 0
                return self._finish(context)

            elif decision == "FINISH":
                print("[Resolve] Resolve-Pipeline abgeschlossen (FINISHED).")
                self._update_progress(context, 100)
                self._subphase = 0
                return self._finish(context)

            elif decision == "ABORT":
                print("[Resolve] Resolve-Pipeline abgebrochen (ABORT).")
                self._subphase = 0
                return self._finish(context, cancelled=True)

        return {'RUNNING_MODAL'}

    # ---------------- Stage Logic ----------------
    # ---------------- NEW: Nur Solve (keine Auswertung) ----------------
    def _run_solve_only(self, context, stage: int) -> bool:
        print(f"\n[Resolve][Stage {stage}] Subphase: Solve")
        refine_intrinsics_reset(context)
        if stage >= 1:
            refine_intrinsics_focal_length_on(context)
        if stage >= 2:
            refine_intrinsics_principal_point_on(context)
        if stage >= 3:
            refine_intrinsics_radial_distortion_on(context)
        return self._solve_camera(context, label=f"Stage {stage}")

    def _get_max_error_value(self, context) -> float:
        scene = context.scene
        # Fallback 2.0, wie von dir gewünscht
        default = 2.0
        val = getattr(scene, "max_error_value", default)
        try:
            return float(val)
        except Exception:
            return default

    def _run_stage0_evaluate(self, context):
        """
        Stage 0:
            - Intrinsics reset
            - Solve (in Subphase 0)
            - Schwelle: avg_error > 10.0
        """
        print("\n[Resolve][Stage 0] Starte Basis-Solve (kein Intrinsics-Refine, Schwelle 10.0).")
        refine_intrinsics_reset(context)
        print("[Resolve][Stage 0] Subphase: Evaluate")
        avg_err = get_average_error(self._space.clip)
        self._avg_error = avg_err
        # Zusätzliche Fehler-Qualifikation
        if avg_err is None or avg_err != avg_err:  # NaN-Check
            print(f"[Resolve][Stage {self._stage}] avg_error ungültig → ABORT.")
            return "ABORT", None
        print(f"[Resolve][Stage 0] Durchschnittsfehler nach Solve: {avg_err}")
        threshold_stage0 = 10.0
        if avg_err is not None and avg_err <= threshold_stage0:
            print(f"[Resolve][Stage 0] avg_error <= {threshold_stage0} → Weiter zu Stage 1.")
            return "NEXT_STAGE", 1
        print(f"[Resolve][Stage 0] avg_error > {threshold_stage0} → Cleanup + Weak-Frame-Check.")
        try:
            deleted = clean_error_tracks(context, sort_desc=True)
            print(f"[Resolve][Stage 0] clean_error_tracks: {deleted} fehlerhafte Tracks gelöscht.")
        except Exception as e:
            print(f"[Resolve][Stage 0] FEHLER in clean_error_tracks: {e}")
        try:
            weak_frame = find_first_weak_frame(context)
        except Exception as e:
            print(f"[Resolve][Stage 0] FEHLER bei find_first_weak_frame: {e}")
            weak_frame = None
        if weak_frame is None:
            print("[Resolve][Stage 0] Kein Weak Frame gefunden → FINISH ohne MasterCycle.")
            return "FINISH", None
        else:
            # Master-Cycle-Eskalationsschutz
            if len(self._space.clip.tracking.tracks) < 5:
                print(f"[Resolve][Stage {self._stage}] Zu wenige Tracks übrig → ABORT.")
                return "ABORT", None
            print(f"[Resolve][Stage 0] Weak Frame gefunden (Frame {weak_frame}) → MASTER_CYCLE.")
            return "MASTER_CYCLE", None

    def _run_stage1_evaluate(self, context):
        """
        Stage 1:
            - Focal Length Refinement (Solve in Subphase 0)
            - Schwelle: avg_error <= max_error_value → FINISH
        """
        max_err = self._get_max_error_value(context)
        print(f"\n[Resolve][Stage 1] Focal-Refine mit max_error_value = {max_err}")
        refine_intrinsics_reset(context)
        refine_intrinsics_focal_length_on(context)
        print("[Resolve][Stage 1] Subphase: Evaluate")
        avg_err = get_average_error(self._space.clip)
        self._avg_error = avg_err
        # Zusätzliche Fehler-Qualifikation
        if avg_err is None or avg_err != avg_err:  # NaN-Check
            print(f"[Resolve][Stage {self._stage}] avg_error ungültig → ABORT.")
            return "ABORT", None
        print(f"[Resolve][Stage 1] Durchschnittsfehler nach Solve: {avg_err}")
        if avg_err is not None and avg_err <= max_err:
            print("[Resolve][Stage 1] avg_error <= max_error_value → FINISH.")
            return "FINISH", None
        print("[Resolve][Stage 1] avg_error > max_error_value → Cleanup + Weak-Frame-Check.")
        try:
            deleted = clean_error_tracks(context, sort_desc=True)
            print(f"[Resolve][Stage 1] clean_error_tracks: {deleted} fehlerhafte Tracks gelöscht.")
        except Exception as e:
            print(f"[Resolve][Stage 1] FEHLER in clean_error_tracks: {e}")
        try:
            weak_frame = find_first_weak_frame(context)
        except Exception as e:
            print(f"[Resolve][Stage 1] FEHLER bei find_first_weak_frame: {e}")
            weak_frame = None
        if weak_frame is None:
            print("[Resolve][Stage 1] Kein Weak Frame gefunden → Weiter zu Stage 2.")
            return "NEXT_STAGE", 2
        else:
            # Master-Cycle-Eskalationsschutz
            if len(self._space.clip.tracking.tracks) < 5:
                print(f"[Resolve][Stage {self._stage}] Zu wenige Tracks übrig → ABORT.")
                return "ABORT", None
            print(f"[Resolve][Stage 1] Weak Frame gefunden (Frame {weak_frame}) → MASTER_CYCLE.")
            return "MASTER_CYCLE", None

    def _run_stage2_evaluate(self, context):
        """
        Stage 2:
            - Focal + Principal (Solve in Subphase 0)
            - Schwelle: avg_error <= max_error_value → FINISH
        """
        max_err = self._get_max_error_value(context)
        print(f"\n[Resolve][Stage 2] Focal + Principal-Refine mit max_error_value = {max_err}")
        refine_intrinsics_reset(context)
        refine_intrinsics_focal_length_on(context)
        refine_intrinsics_principal_point_on(context)
        print("[Resolve][Stage 2] Subphase: Evaluate")
        avg_err = get_average_error(self._space.clip)
        self._avg_error = avg_err
        # Zusätzliche Fehler-Qualifikation
        if avg_err is None or avg_err != avg_err:  # NaN-Check
            print(f"[Resolve][Stage {self._stage}] avg_error ungültig → ABORT.")
            return "ABORT", None
        print(f"[Resolve][Stage 2] Durchschnittsfehler nach Solve: {avg_err}")
        if avg_err is not None and avg_err <= max_err:
            print("[Resolve][Stage 2] avg_error <= max_error_value → FINISH.")
            return "FINISH", None
        print("[Resolve][Stage 2] avg_error > max_error_value → Cleanup + Weak-Frame-Check.")
        try:
            deleted = clean_error_tracks(context, sort_desc=True)
            print(f"[Resolve][Stage 2] clean_error_tracks: {deleted} fehlerhafte Tracks gelöscht.")
        except Exception as e:
            print(f"[Resolve][Stage 2] FEHLER in clean_error_tracks: {e}")
        try:
            weak_frame = find_first_weak_frame(context)
        except Exception as e:
            print(f"[Resolve][Stage 2] FEHLER bei find_first_weak_frame: {e}")
            weak_frame = None
        if weak_frame is None:
            print("[Resolve][Stage 2] Kein Weak Frame gefunden → Weiter zu Stage 3.")
            return "NEXT_STAGE", 3
        else:
            # Master-Cycle-Eskalationsschutz
            if len(self._space.clip.tracking.tracks) < 5:
                print(f"[Resolve][Stage {self._stage}] Zu wenige Tracks übrig → ABORT.")
                return "ABORT", None
            print(f"[Resolve][Stage 2] Weak Frame gefunden (Frame {weak_frame}) → MASTER_CYCLE.")
            return "MASTER_CYCLE", None

    def _run_stage3_evaluate(self, context):
        """
        Stage 3:
            - Focal + Principal + Radial (Solve in Subphase 0)
        """
        max_err = self._get_max_error_value(context)
        print(f"\n[Resolve][Stage 3] Focal + Principal + Radial-Refine mit max_error_value = {max_err}")
        refine_intrinsics_reset(context)
        refine_intrinsics_focal_length_on(context)
        refine_intrinsics_principal_point_on(context)
        refine_intrinsics_radial_distortion_on(context)
        print("[Resolve][Stage 3] Subphase: Evaluate")
        avg_err = get_average_error(self._space.clip)
        self._avg_error = avg_err
        # Zusätzliche Fehler-Qualifikation
        if avg_err is None or avg_err != avg_err:  # NaN-Check
            print(f"[Resolve][Stage {self._stage}] avg_error ungültig → ABORT.")
            return "ABORT", None
        print(f"[Resolve][Stage 3] Durchschnittsfehler nach Solve: {avg_err}")
        if avg_err is not None and avg_err <= max_err:
            print("[Resolve][Stage 3] avg_error <= max_error_value → FINISH.")
            return "FINISH", None
        print("[Resolve][Stage 3] avg_error > max_error_value → Cleanup + Weak-Frame-Check.")
        try:
            deleted = clean_error_tracks(context, sort_desc=True)
            print(f"[Resolve][Stage 3] clean_error_tracks: {deleted} fehlerhafte Tracks gelöscht.")
        except Exception as e:
            print(f"[Resolve][Stage 3] FEHLER in clean_error_tracks: {e}")
        try:
            weak_frame = find_first_weak_frame(context)
        except Exception as e:
            print(f"[Resolve][Stage 3] FEHLER bei find_first_weak_frame: {e}")
            weak_frame = None
        if weak_frame is None:
            print("[Resolve][Stage 3] Kein Weak Frame gefunden → FINISH (kein MasterCycle mehr).")
            return "FINISH", None
        else:
            # Master-Cycle-Eskalationsschutz
            if len(self._space.clip.tracking.tracks) < 5:
                print(f"[Resolve][Stage {self._stage}] Zu wenige Tracks übrig → ABORT.")
                return "ABORT", None
            print(f"[Resolve][Stage 3] Weak Frame gefunden (Frame {weak_frame}) → MASTER_CYCLE.")
            return "MASTER_CYCLE", None

    # ---------------- Solve Helper ----------------

    def _solve_camera(self, context, label: str) -> bool:
        """
        Führt den Solve mit Clip-Editor-Override aus.
        Gibt True/False zurück, je nach Erfolg.
        """
        print(f"[Resolve][{label}] Führe Solve (clip.solve_camera) aus ...")
        if not (self._area and self._region and self._space):
            print(f"[Resolve][{label}] Kein gültiger Clip-Editor-Kontext → Solve-Abbruch.")
            return False

        try:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')

                # -----------------------------------------
                # Post-Solve: Entferne nicht rekonstruierbare Tracks
                # -----------------------------------------
                try:
                    clip = self._space.clip
                    tracking = clip.tracking
                    reconstructed = tracking.reconstruction

                    if reconstructed and hasattr(reconstructed, "points"):
                        bad = []
                        for track in tracking.tracks:
                            if track.name not in reconstructed.points:
                                bad.append(track.name)

                        if bad:
                            print(f"[Resolve][{label}] Entferne {len(bad)} nicht rekonstruierbare Tracks.")
                            from ...Helper.delete import delete_tracks_by_names
                            delete_tracks_by_names(clip, bad)
                            clip.tracking.objects.active.reconstruction.is_valid = False
                except Exception as e:
                    print(f"[Resolve][{label}] Fehler bei Post-Solve-Cleanup: {e}")

            out_log = buf_out.getvalue().strip()
            err_log = buf_err.getvalue().strip()
            if out_log:
                print(f"[Resolve][{label}] Solve STDOUT:\n{out_log}")
            if err_log:
                print(f"[Resolve][{label}] Solve STDERR:\n{err_log}")
            print(f"[Resolve][{label}] Solve erfolgreich beendet.")
            return True
        except Exception as e:
            print(f"[Resolve][{label}] Solve fehlgeschlagen: {e}")
            return False

    # ---------------- Helpers ----------------
    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

    def _update_progress(self, context, value: int):
        """Aktualisiert die string-basierte Fortschritts-UI (z.B. '75 %')."""
        scene = context.scene
        percent_str = f"{value} %"
        if hasattr(scene, "kaiserlich_progress_title"):
            scene.kaiserlich_progress_title = percent_str
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        area.tag_redraw()

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        if cancelled:
            print("[Resolve] Operator abgebrochen.")
            return {'CANCELLED'}
        else:
            print("[Resolve] Operator abgeschlossen.")
            return {'FINISHED'}


# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
