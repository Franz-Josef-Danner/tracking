# Operator/Master/master_resolve_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator
import io
import contextlib

# --- Helper ---------------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
except Exception as e:
    raise ImportError(f"[master_resolve_operator_modal] Fehlende Add-on-Module: {e}")


class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Modaler Solve → Polling auf average_error → CleanError (mit Logs)."""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (modal+poll)"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Error Threshold",
        description="Threshold für anschließenden Clean-Error-Schritt",
        default=20.0
    )
    action: bpy.props.EnumProperty(
        items=[('DELETE_TRACK', "Delete Track", ""), ('DELETE_SEGMENT', "Delete Segment", "")],
        default='DELETE_TRACK'
    )
    poll_interval: bpy.props.FloatProperty(
        name="Poll-Intervall (s)",
        default=0.25, min=0.05, soft_max=1.0
    )
    timeout_seconds: bpy.props.FloatProperty(
        name="Timeout (s)",
        default=8.0, min=1.0, soft_max=60.0
    )
    log_verbose: bpy.props.BoolProperty(
        name="Verbose Logs",
        default=True
    )

    _timer = None
    _phase = 0
    _area = _region = _space = None
    _elapsed = 0.0
    _avg_error = None
    _solve_done_frame = None

    # ---------------- Lifecycle ----------------
    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 0
        self._elapsed = 0.0
        self._avg_error = None
        self._solve_done_frame = None
        self._log_info("[Resolve][Init] Modal gestartet.")
        self._update_ui(context, "Init …", 5)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Phase 0: Kontext finden
        if self._phase == 0:
            self._area, self._region, self._space = self._find_clip_context()
            if not (self._area and self._region and self._space and getattr(self._space, "clip", None)):
                self._log_error("[Resolve][Phase0] Kein CLIP_EDITOR/Clip gefunden.")
                return self._finish(context, cancelled=True)
            self._log_info("[Resolve][Phase0] Kontext ok → Phase1 (Solve).")
            self._update_ui(context, "Starte Solve …", 15)
            self._phase = 1
            return {'RUNNING_MODAL'}

        # Phase 1: Solve
        if self._phase == 1:
            try:
                self._log_info("[Resolve][Phase1] Solve aufgerufen (Logs stumm).")
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                if self.log_verbose:
                    out_len = len(buf_out.getvalue())
                    err_len = len(buf_err.getvalue())
                    self._log_dbg(f"[Resolve][Phase1] Solve stdout={out_len}B, stderr={err_len}B (unterdrückt).")
                self._solve_done_frame = context.scene.frame_current
                self._update_ui(context, "Solve abgeschlossen. Prüfe Ergebnis …", 40)
                self._log_info(f"[Resolve][Phase1] Solve done @ frame {self._solve_done_frame}. → Phase2 (Polling).")
            except Exception as e:
                self._log_error(f"[Resolve][Phase1] Solve fehlgeschlagen: {e}")
                return self._finish(context, cancelled=True)
            self._phase = 2
            return {'RUNNING_MODAL'}

        # Phase 2: Polling auf average_error / reconstruction
        if self._phase == 2:
            self._elapsed += self.poll_interval
            clip = getattr(self._space, "clip", None)
            recon_ok, err_val = False, None

            if clip:
                recon_ok = self._is_reconstruction_valid(clip)
                err_val = self._safe_avg_error(clip)

            if self.log_verbose:
                self._log_dbg(f"[Resolve][Phase2] t={self._elapsed:.2f}s, recon_ok={recon_ok}, avg_err={err_val}")

            if recon_ok or (err_val is not None and err_val == err_val):
                self._avg_error = err_val
                msg = f"avg_error={err_val:.4f}" if isinstance(err_val, (int, float)) else "Reconstruction valid"
                self._log_info(f"[Resolve][Phase2] Ergebnis erkannt: {msg}. → Phase3 (CleanError).")
                self._update_ui(context, f"Solve fertig ({msg}). Starte CleanError …", 75)
                self._phase = 3
                return {'RUNNING_MODAL'}

            if self._elapsed >= self.timeout_seconds:
                self._log_warn("[Resolve][Phase2] Timeout: Kein average_error sichtbar – fahre fort.")
                self._phase = 3
                return {'RUNNING_MODAL'}

            prog = min(70, 40 + (self._elapsed / max(0.001, self.timeout_seconds)) * 30)
            self._update_ui(context, "Warte auf average_error …", prog)
            return {'RUNNING_MODAL'}

        # Phase 3: CleanError-Übergabe
        if self._phase == 3:
            try:
                self._log_info(f"[Resolve][Phase3] CleanError start …")
                bpy.ops.kaiserlich_tracker.clean_error_operator('INVOKE_DEFAULT')
                self._log_info("[Resolve][Phase3] Übergabe an CleanError ok.")
            except Exception as e:
                self._log_error(f"[Resolve][Phase3] CleanError Start fehlgeschlagen: {e}")
                return self._finish(context, cancelled=True)

            if isinstance(self._avg_error, (int, float)):
                self._report_info(f"[Resolve] Durchschnittsfehler: {self._avg_error:.4f}")
            self._update_ui(context, "Fertig.", 100)
            return self._finish(context)

        return {'RUNNING_MODAL'}

    # ---------------- Helpers ----------------
    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

    def _is_reconstruction_valid(self, clip) -> bool:
        try:
            recon = clip.tracking.reconstruction
            return bool(recon and recon.is_valid)
        except Exception:
            return False

    def _safe_avg_error(self, clip):
        try:
            return get_average_error(clip)
        except Exception:
            return None

    def _update_ui(self, context, label: str, percent: float):
        scene = context.scene
        scene.kaiserlich_progress_title = label
        scene.kaiserlich_progress_step = f"{int(max(0, min(100, percent)))}%"
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._phase = 0
        self._log_info(f"[Resolve][Finish] Modalvorgang {'abgebrochen' if cancelled else 'abgeschlossen'}.")
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    # ---------------- Logging ----------------
    def _report_info(self, msg: str):
        self.report({'INFO'}, msg)

    def _log_info(self, msg: str):
        if self.log_verbose:
            print(msg)
        self._report_info(msg)

    def _log_warn(self, msg: str):
        if self.log_verbose:
            print(msg)
        self.report({'WARNING'}, msg)

    def _log_error(self, msg: str):
        print(msg)
        self.report({'ERROR'}, msg)

    def _log_dbg(self, msg: str):
        if self.log_verbose:
            print(msg)


# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
