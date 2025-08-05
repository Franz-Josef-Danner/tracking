import bpy
from bpy.types import Operator

class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts"

    _timer = None
    _step = 0
    _start_frame = 0

    def execute(self, context):
        self._step = 0
        self._start_frame = context.scene.frame_current  # Speichert die aktuelle Frame-Position
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        print("[Tracking] Schritt: 0")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        clip = context.space_data.clip
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            return {'CANCELLED'}

        if self._step == 0:
            print("→ Starte Vorwärts-Tracking...")
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            print("→ Warte auf Abschluss des Vorwärts-Trackings...")
            context.scene.frame_current = self._start_frame  # Zurück zum Ursprungsframe
            self._step += 1
            print(f"← Frame zurückgesetzt auf {self._start_frame}")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("✓ Rückwärts-Tracking abgeschlossen.")
            print("✓ Bidirektionales Tracking beendet.")
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}
