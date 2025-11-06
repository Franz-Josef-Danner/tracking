from __future__ import annotations
import bpy
from bpy.types import Operator

# --- Helper-Importe ---------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
except Exception as e:
    raise ImportError(f"[master_resolve_operator_modal] Fehlende Add-on-Module: {e}")

class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Modaler Solve mit sichtbarem Fortschritt und CleanError-Übergabe."""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (modal)"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Error Threshold",
        description="Threshold für anschließenden Clean-Error-Schritt",
        default=20.0
    )
    action: bpy.props.EnumProperty(
        items=[
            ('DELETE_TRACK', "Delete Track", ""),
            ('DELETE_SEGMENT', "Delete Segment", ""),
        ],
        default='DELETE_TRACK'
    )

    _timer = None
    _phase = 0
    _avg_error = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.3, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 0
        self.report({'INFO'}, "[Resolve] Modal gestartet – Phase 0 (Initialisierung).")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # --- Phase 0: Setup / Clip finden ---
        if self._phase == 0:
            area, region, space = self._find_clip_context()
            if not (area and region and space):
                self.report({'ERROR'}, "[Resolve] Kein CLIP_EDITOR Kontext gefunden.")
                return self._finish(context, cancelled=True)
            self._area, self._region, self._space = area, region, space
            self._phase = 1
            self._update_ui_progress(context, "Solve läuft …", 20)
            return {'RUNNING_MODAL'}

        # --- Phase 1: Solve ausführen ---
        elif self._phase == 1:
            try:
                with bpy.context.temp_override(area=self._area, region=self._region, space_data=self._space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                self.report({'INFO'}, "[Resolve] Solve abgeschlossen.")
            except Exception as e:
                self.report({'ERROR'}, f"[Resolve] Fehler beim Solve: {e}")
                return self._finish(context, cancelled=True)
            self._phase = 2
            self._update_ui_progress(context, "Berechne durchschnittlichen Fehler …", 50)
            return {'RUNNING_MODAL'}

        # --- Phase 2: Fehler messen ---
        elif self._phase == 2:
            clip = getattr(self._space, "clip", None)
            if clip:
                try:
                    self._avg_error = get_average_error(clip)
                    self.report({'INFO'}, f"[Resolve] Durchschnittsfehler: {self._avg_error:.4f}")
                except Exception as e:
                    self.report({'WARNING'}, f"[Resolve] Fehler bei get_average_error: {e}")
            self._phase = 3
            self._update_ui_progress(context, "Starte CleanError …", 75)
            return {'RUNNING_MODAL'}

        # --- Phase 3: CleanError starten ---
        elif self._phase == 3:
            try:
                bpy.ops.kaiserlich_tracker.clean_error_modal(
                    'INVOKE_DEFAULT',
                    threshold=self.threshold,
                    action=self.action
                )
                self.report({'INFO'}, f"[Resolve] Übergabe an CleanError (Threshold={self.threshold:.3f}).")
            except Exception as e:
                self.report({'ERROR'}, f"[Resolve] Fehler bei Übergabe an CleanError: {e}")
            self._phase = 4
            self._update_ui_progress(context, "Abschluss …", 100)
            return {'RUNNING_MODAL'}

        # --- Phase 4: Fertig ---
        elif self._phase == 4:
            return self._finish(context)

        return {'RUNNING_MODAL'}

    # -------------------------------------------------------
    # Hilfsfunktionen
    # -------------------------------------------------------

    def _find_clip_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    return area, region, area.spaces.active
        return None, None, None

    def _update_ui_progress(self, context, label: str, percent: float):
        """Aktualisiert Szene-Properties für UI-Fortschritt."""
        scene = context.scene
        scene.kaiserlich_progress_title = f"{label}"
        scene.kaiserlich_progress_step = f"{int(percent)}%"
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
        msg = "abgebrochen" if cancelled else "abgeschlossen"
        self.report({'INFO'}, f"[Resolve] Modalvorgang {msg}.")
        return {'CANCELLED'} if cancelled else {'FINISHED'}


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)