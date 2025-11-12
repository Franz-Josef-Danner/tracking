# master_resolve_operator
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
    """Multi-Stage Camera Solve Operator with Intrinsics Escalation and Post-Solve Cleanup"""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (staged)"
    bl_description = (
        "Executes the camera solve in multiple escalating refinement stages, "
        "runs cleanup after each solve, and triggers Master Cycle if weak frames are found."
    )
    bl_options = {'REGISTER', 'UNDO'}

    poll_interval: bpy.props.FloatProperty(default=0.25)
    timeout_seconds: bpy.props.FloatProperty(default=8.0)

    _timer = None
    _phase = 0
    _stage = 0
    _elapsed = 0.0
    _avg_error = None
    _area = _region = _space = None

    MAX_STAGES = 4

    # ---------------- Lifecycle ----------------
    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 0
        self._stage = 0
        self._elapsed = 0.0
        self._update_progress(context, 0)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # --- PHASE 0: Locate Clip Editor ----------------------------------
        if self._phase == 0:
            print("\n[Resolve][Phase 0] Suche nach Clip Editor Kontext ...")
            self._area, self._region, self._space = self._find_clip_context()
            if not (self._space and getattr(self._space, "clip", None)):
                print("[Resolve][Phase 0] Kein Clip Editor gefunden → Abbruch.")
                return self._finish(context, cancelled=True)
            print("[Resolve][Phase 0] Clip Editor gefunden → Wechsel zu Phase 1 (Solve-Start)")
            self._phase = 1
            self._stage = 1
            return {'RUNNING_MODAL'}

        # --- PHASE 1: Solve + Cleanup + Weak Frame Check ------------------
        if self._phase == 1:
            if self._stage > self.MAX_STAGES:
                self._update_progress(context, 100)
                print("[Resolve][Phase 1] Alle Stages abgeschlossen → Beende Operator.")
                # Finaler globaler Cleanup nach allen Solves
                try:
                    print("[Resolve][Final] Alle Stages abgeschlossen → Starte abschließenden Cleanup-Operator ...")
                    bpy.ops.kaiserlich_tracker.clean_error_operator('EXEC_DEFAULT')
                    print("[Resolve][Final] Cleanup-Operator erfolgreich ausgeführt.")
                except Exception as e:
                    print(f"[Resolve][Final] FEHLER beim finalen Cleanup: {e}")
                return self._finish(context)

            print(f"\n[Resolve][Stage {self._stage}] Starte Solve-Phase ...")
            self._run_solve_stage(context, self._stage)
            print(f"[Resolve][Stage {self._stage}] Solve abgeschlossen.")

            # Zwischen-Solve: interner Cleanup über Helper
            try:
                print(f"[Resolve][Stage {self._stage}] Starte Zwischen-Cleanup (Helper clean_error_tracks) ...")
                deleted = clean_error_tracks(context, sort_desc=True)
                print(f"[Resolve][Stage {self._stage}] Zwischen-Cleanup abgeschlossen → {deleted} fehlerhafte Tracks gelöscht.")
            except Exception as e:
                print(f"[Resolve][Stage {self._stage}] FEHLER im Zwischen-Cleanup: {e}")
                self.report({'WARNING'}, f"Intermediate cleanup failed: {e}")

            try:
                print(f"[Resolve][Stage {self._stage}] Suche nach weak frame ...")
                weak_frame = find_first_weak_frame(context)
                if weak_frame is not None:
                    print(f"[Resolve][Stage {self._stage}] Weak Frame gefunden → Übergabe an MasterCycle (Frame {weak_frame}) ...")
                    bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                    self._update_progress(context, 100)
                    return self._finish(context)
                else:
                    print(f"[Resolve][Stage {self._stage}] Kein Weak Frame gefunden.")
            except Exception as e:
                print(f"[Resolve][Stage {self._stage}] FEHLER bei Weak Frame Check: {e}")
                self.report({'WARNING'}, f"Weak frame check failed: {e}")

            self._stage += 1
            progress = int((self._stage - 1) / self.MAX_STAGES * 100)
            self._update_progress(context, progress)
            print(f"[Resolve][Stage {self._stage - 1}] Weiter zu Stage {self._stage} (Progress: {progress}%)")
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ---------------- Solve Logic ----------------
    def _run_solve_stage(self, context, stage: int):
        """Executes a solve with predefined intrinsic refinement settings."""
        print(f"[Resolve][Stage {stage}] Setze Intrinsics-Parameter zurück ...")
        refine_intrinsics_reset(context)
        if stage == 1:
            print("[Resolve][Stage 1] Basis-Solve (keine Intrinsics-Verfeinerung)")
            pass
        elif stage == 2:
            print("[Resolve][Stage 2] Aktiviere Focal Length Refinement")
            refine_intrinsics_focal_length_on(context)
        elif stage == 3:
            print("[Resolve][Stage 3] Aktiviere Focal Length + Principal Point Refinement")
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
        elif stage == 4:
            print("[Resolve][Stage 4] Aktiviere Focal Length + Principal Point + Radial Distortion Refinement")
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            refine_intrinsics_radial_distortion_on(context)

        try:
            print(f"[Resolve][Stage {stage}] Führe Solve aus (clip.solve_camera) ...")
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')
            out_log = buf_out.getvalue().strip()
            err_log = buf_err.getvalue().strip()
            if out_log:
                print(f"[Resolve][Stage {stage}] Solve STDOUT:\n{out_log}")
            if err_log:
                print(f"[Resolve][Stage {stage}] Solve STDERR:\n{err_log}")
            print(f"[Resolve][Stage {stage}] Solve erfolgreich beendet.")
        except Exception as e:
            print(f"[Resolve][Stage {stage}] Solve fehlgeschlagen: {e}")

    # ---------------- Helpers ----------------
    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

    def _update_progress(self, context, value: int):
        """Updates the string-based UI property for progress (e.g., '75 %')."""
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
        if cancelled:
            print("[Resolve] Operator abgebrochen.")
        else:
            print("[Resolve] Operator abgeschlossen.")
        return {'CANCELLED'} if cancelled else {'FINISHED'}


# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
