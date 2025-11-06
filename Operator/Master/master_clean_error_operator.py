# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator

class KAISERLICHTRACKER_OT_clean_error_modal(Operator):
    """Non-blocking Wrapper für bpy.ops.clip.clean_error"""
    bl_idname = "kaiserlich_tracker.clean_error_modal"
    bl_label = "Clean Error (modal async)"
    bl_options = {'REGISTER', 'INTERNAL'}

    threshold: bpy.props.FloatProperty(default=10.0)
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
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # nur einmal ausführen, dann beenden
        if not self._started:
            self._started = True
            try:
                area = None
                region = None
                space = None
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
                    bpy.ops.clip.clean_error('EXEC_DEFAULT',
                                             action=self.action,
                                             threshold=self.threshold)
                    self.report({'INFO'},
                                f"Clean Error ausgeführt (Threshold={self.threshold:.3f})")
            except Exception as e:
                self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e}")

            # Nach erfolgreichem Clean → Master-Cycle aufrufen (asynchron)
            try:
                self.report({'INFO'}, "[CleanError] Starte Master-Cycle nach erfolgreichem Clean …")

                # Sicherheit: Prüfen, ob Operator vorhanden
                op_id = "kaiserlich_tracker.master_cycle_operator"
                if hasattr(bpy.ops.kaiserlich_tracker, "master_cycle_operator"):
                    # Asynchroner Aufruf (non-blocking)
                    bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                    self.report({'INFO'}, "[CleanError] Übergabe an Master-Cycle erfolgreich.")
                else:
                    self.report({'WARNING'},
                                f"[CleanError] Operator '{op_id}' nicht gefunden oder nicht registriert.")

            except Exception as handoff_err:
                self.report({'ERROR'},
                            f"[CleanError] Fehler bei Übergabe an Master-Cycle: {handoff_err}")

            # Operator selbst beenden
            return self._finish(context)
        return {'RUNNING_MODAL'}

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        return {'CANCELLED'} if cancelled else {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_modal)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_modal)
