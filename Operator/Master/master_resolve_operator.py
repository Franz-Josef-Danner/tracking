from __future__ import annotations
import bpy
from bpy.types import Operator

# --- Helper ---------------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
except Exception as e:
    raise ImportError(f"[master_resolve_operator_modal] Fehlende Add-on-Module: {e}")

class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Modaler Solve → Polling auf average_error → CleanError."""
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
        description="Abbruch, falls average_error nicht innerhalb dieser Zeit auftaucht",
        default=8.0, min=1.0, soft_max=30.0
    )

    _timer = None
    _phase = 0
    _area = _region = _space = None
    _elapsed = 0.0
    _avg_error = None
    _solve_done_frame = None

    def invoke(self, context, event):
        # Timer mit konfigurierbarem Intervall
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 0
        self._elapsed = 0.0
        self._avg_error = None
        self._solve_done_frame = None
        self._update_ui(context, "Init …", 5)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Phase 0: Clip-Editor-Kontext suchen
        if self._phase == 0:
            self._area, self._region, self._space = self._find_clip_context()
            if not (self._area and self._region and self._space and getattr(self._space, "clip", None)):
                self.report({'ERROR'}, "[Resolve] Kein CLIP_EDITOR/Clip gefunden.")
                return self._finish(context, cancelled=True)
            self._update_ui(context, "Starte Solve …", 15)
            self._phase = 1
            return {'RUNNING_MODAL'}

        # Phase 1: Solve EINMAL ausführen (blocking in diesem Tick), dann in Phase 2 wechseln
        if self._phase == 1:
            try:
                with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')  # blocking call in diesem Timer-Tick
                self._solve_done_frame = context.scene.frame_current
                self._update_ui(context, "Solve abgeschlossen. Prüfe Ergebnis …", 40)
            except Exception as e:
                self.report({'ERROR'}, f"[Resolve] Solve fehlgeschlagen: {e}")
                return self._finish(context, cancelled=True)
            self._phase = 2
            return {'RUNNING_MODAL'}

        # Phase 2: Polling – warte, bis average_error/Reconstruction valide ist
        if self._phase == 2:
            self._elapsed += self.poll_interval
            clip = getattr(self._space, "clip", None)
            recon_ok = False
            err_val = None

            if clip:
                try:
                    # robust: erst Rekonstruktion prüfen, dann Helper
                    recon = clip.tracking.reconstruction
                    recon_ok = bool(recon and recon.is_valid)
                except Exception:
                    pass

                try:
                    err_val = get_average_error(clip)
                except Exception:
                    err_val = None

            if recon_ok or (err_val is not None and err_val == err_val):  # NaN-Schutz
                self._avg_error = err_val
                msg = f"avg_error={err_val:.4f}" if isinstance(err_val, (int, float)) else "Reconstruction valid"
                self._update_ui(context, f"Solve fertig ({msg}). Starte CleanError …", 75)
                self._phase = 3
                return {'RUNNING_MODAL'}

            # Timeout?
            if self._elapsed >= self.timeout_seconds:
                self.report({'WARNING'}, "[Resolve] Timeout: Kein average_error sichtbar.")
                self._phase = 3  # trotzdem weiter – je nach Strategie
                return {'RUNNING_MODAL'}

            # weiter pollen
            self._update_ui(context, "Warte auf average_error …", min(70, 40 + (self._elapsed / max(0.001, self.timeout_seconds)) * 30))
            return {'RUNNING_MODAL'}

        # Phase 3: CleanError nicht-blockierend anstoßen
        if self._phase == 3:
            try:
                bpy.ops.kaiserlich_tracker.clean_error_modal(
                    'INVOKE_DEFAULT',
                    threshold=self.threshold,
                    action=self.action
                )
            except Exception as e:
                self.report({'ERROR'}, f"[Resolve] CleanError Start fehlgeschlagen: {e}")
                return self._finish(context, cancelled=True)

            # UI-Info finalisieren
            if isinstance(self._avg_error, (int, float)):
                self.report({'INFO'}, f"[Resolve] Durchschnittsfehler: {self._avg_error:.4f}")
            self._update_ui(context, "Fertig.", 100)
            return self._finish(context)

        return {'RUNNING_MODAL'}

    # ----------------- Helpers -----------------
    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

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
        return {'CANCELLED'} if cancelled else {'FINISHED'}

# --------- Registration ----------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)