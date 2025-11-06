# Operator/Master/master_clean_error_operator.py
import bpy
import traceback
from bpy.types import Operator


class KAISERLICHTRACKER_OT_clean_error_modal(Operator):
    """Modaler (nicht-blockierender) Wrapper für bpy.ops.clip.clean_error"""
    bl_idname = "kaiserlich_tracker.clean_error_modal"
    bl_label = "Clean Error (Modal Async)"
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
    _phase = 0
    _done = False

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "[CleanError] Async Start …")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Schritt 1: Setup (einmalig)
        if self._phase == 0:
            self._phase = 1
            bpy.app.timers.register(self._execute_clean_async, first_interval=0.05)
            return {'RUNNING_MODAL'}

        # Schritt 2: Warten bis fertig
        if self._done:
            return self._finish(context)

        return {'RUNNING_MODAL'}

    def _execute_clean_async(self):
        """Wird über bpy.app.timers im Hintergrund ausgeführt"""
        try:
            # Sicheren Kontext finden
            area = region = space = None
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
                self._done = True
                return None

            # CleanError ausführen
            with bpy.context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.clean_error(
                    'EXEC_DEFAULT',
                    action=self.action,
                    threshold=self.threshold
                )

            self.report({'INFO'}, f"[CleanError] abgeschlossen (Threshold={self.threshold:.2f})")

            # Danach MasterCycle anstoßen
            bpy.app.timers.register(self._invoke_master_cycle, first_interval=0.1)

        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"[CleanError] Fehler: {e}")

        # Markiere als abgeschlossen
        self._done = True
        return None

    def _invoke_master_cycle(self):
        """Startet den MasterCycle asynchron nach dem Clean"""
        try:
            op_id = "kaiserlich_tracker.master_cycle_operator"
            if hasattr(bpy.ops.kaiserlich_tracker, "master_cycle_operator"):
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
                self.report({'INFO'}, "[CleanError] Master-Cycle gestartet.")
            else:
                self.report({'WARNING'}, f"[CleanError] '{op_id}' nicht registriert.")
        except Exception as e:
            self.report({'ERROR'}, f"[CleanError] Fehler bei Übergabe: {e}")
        return None

    def _finish(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self.report({'INFO'}, "[CleanError] Modal beendet.")
        return {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_modal)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_modal)
