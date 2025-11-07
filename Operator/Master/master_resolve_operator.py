# Operator/Master/master_resolve_operator.py
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
except Exception as e:
    raise ImportError(f"[master_resolve_operator] Fehlende Add-on-Module: {e}")


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (gestuft)"
    bl_discription = "Survey what was gained, and what was lost."
    bl_options = {'REGISTER', 'UNDO'}
    poll_interval: bpy.props.FloatProperty(default=0.25)
    timeout_seconds: bpy.props.FloatProperty(default=8.0)

    _timer = None
    _phase = 0
    _stage = 0
    _elapsed = 0.0
    _avg_error = None
    _area = _region = _space = None

    MAX_STAGES = 4  # Anzahl der Solve-Stufen

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

        # --- PHASE 0: Clip-Editor finden ----------------------------------
        if self._phase == 0:
            self._area, self._region, self._space = self._find_clip_context()
            if not (self._space and getattr(self._space, "clip", None)):
                return self._finish(context, cancelled=True)
            self._phase = 1
            self._stage = 1
            return {'RUNNING_MODAL'}

        # --- PHASE 1: Solve-Sequenz --------------------------------------
        if self._phase == 1:
            if self._stage > self.MAX_STAGES:
                bpy.ops.kaiserlich_tracker.clean_error_operator('INVOKE_DEFAULT')
                self._update_progress(context, 100)
                return self._finish(context)

            self._run_solve_stage(context, self._stage)
            self._phase = 2
            self._elapsed = 0.0
            progress = int((self._stage - 1) / self.MAX_STAGES * 100)
            self._update_progress(context, progress)
            return {'RUNNING_MODAL'}

        # --- PHASE 2: Polling nach Solve ---------------------------------
        if self._phase == 2:
            self._elapsed += self.poll_interval
            clip = getattr(self._space, "clip", None)
            err_val = self._safe_avg_error(clip)
            max_err = getattr(context.scene, "max_error_value", 20.0)

            if err_val is not None:
                self._avg_error = err_val
                if err_val <= max_err:
                    self._update_progress(context, 100)
                    return self._finish(context)

                # Wenn zu hoch → nächste Stufe
                self._stage += 1
                self._phase = 1
                progress = int((self._stage - 1) / self.MAX_STAGES * 100)
                self._update_progress(context, progress)
                return {'RUNNING_MODAL'}

            if self._elapsed >= self.timeout_seconds:
                self._stage += 1
                self._phase = 1
                progress = int((self._stage - 1) / self.MAX_STAGES * 100)
                self._update_progress(context, progress)
                return {'RUNNING_MODAL'}

            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ---------------- Solve Logic ----------------
    def _run_solve_stage(self, context, stage: int):
        """Führt den Solve mit definierten Intrinsics-Settings aus."""
        refine_intrinsics_reset(context)

        # Stage-Konfiguration
        if stage == 1:
            pass  # Focal=False, Principal=False, Dist=False
        elif stage == 2:
            refine_intrinsics_focal_length_on(context)
        elif stage == 3:
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
        elif stage == 4:
            refine_intrinsics_focal_length_on(context)
            refine_intrinsics_principal_point_on(context)
            refine_intrinsics_radial_distortion_on(context)

        # Ausführung Solve
        try:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')
        except Exception:
            pass

    # ---------------- Helpers ----------------
    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

    def _safe_avg_error(self, clip):
        try:
            return get_average_error(clip)
        except Exception:
            return None

    def _update_progress(self, context, value: int):
        """Aktualisiert String-UI-Property für Fortschritt (z. B. '75 %')."""
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
        return {'CANCELLED'} if cancelled else {'FINISHED'}

# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
