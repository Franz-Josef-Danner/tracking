# Operator/Master/master_resolve_operator_modal.py
from __future__ import annotations
import bpy
from bpy.types import Operator

# --- Helper-Importe ---------------------------------------------------------
try:
    from ...Helper.get_average_error import get_average_error
except Exception as e:
    raise ImportError(f"[master_resolve_operator_modal] Fehlende Add-on-Module: {e}")

# ---------------------------------------------------------------------------
# Haupt-Operator – ein einziger Solve, dann Übergabe an CleanError
# ---------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Einfacher, modaler Solve-Durchgang mit direkter Übergabe an CleanError."""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (einfach)"
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
    _started = False

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "[Resolve] Modal gestartet – führe Solve einmalig aus …")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if not self._started:
            self._started = True
            try:
                # --- Solve einmalig ausführen ---
                area, region, space = None, None, None
                for window in bpy.context.window_manager.windows:
                    for area_iter in window.screen.areas:
                        if area_iter.type == 'CLIP_EDITOR':
                            area = area_iter
                            for r in area.regions:
                                if r.type == 'WINDOW':
                                    region = r
                                    break
                            space = area.spaces.active
                            break
                    if area:
                        break

                if not (area and region and space):
                    self.report({'ERROR'}, "Kein CLIP_EDITOR Kontext gefunden.")
                    return self._finish(context, cancelled=True)

                with bpy.context.temp_override(area=area, region=region, space_data=space):
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                    self.report({'INFO'}, "[Resolve] Solve ausgeführt.")

                # --- Fehler messen (optional log only) ---
                clip = getattr(space, "clip", None)
                if clip:
                    avg_err = get_average_error(clip)
                    self.report({'INFO'}, f"[Resolve] Durchschnittsfehler: {avg_err:.4f}")

                # --- Direkt an CleanError weitergeben ---
                try:
                    self.report({'INFO'}, f"[Resolve] Übergabe an CleanError (Threshold={self.threshold:.3f}) …")
                    bpy.ops.kaiserlich_tracker.clean_error_modal(
                        'INVOKE_DEFAULT',
                        threshold=self.threshold,
                        action=self.action
                    )
                    self.report({'INFO'}, "[Resolve] CleanError erfolgreich gestartet.")
                except Exception as handoff_err:
                    self.report({'ERROR'}, f"[Resolve] Fehler bei Übergabe an CleanError: {handoff_err}")

            except Exception as e:
                self.report({'ERROR'}, f"[Resolve] Fehler im Solve-Durchgang: {e}")

            return self._finish(context)

        return {'RUNNING_MODAL'}

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._started = False
        return {'CANCELLED'} if cancelled else {'FINISHED'}


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_resolve_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_resolve_operator)
