import bpy
from bpy.types import Operator

class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts (sichtbar im UI) und signalisiert Fertig an Orchestrator"

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    def execute(self, context):
        # Flags für Orchestrator setzen
        context.scene["bidi_active"] = True
        context.scene["bidi_result"] = ""

        self._step = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1
        self._start_frame = context.scene.frame_current

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        print("[Tracking] Schritt: 0 (Start Bidirectional Track)")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            return self._finish(context, result="FAILED")

        if self._step == 0:
            print("→ Starte Vorwärts-Tracking...")
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            print("→ Warte auf Abschluss des Vorwärts-Trackings...")
            context.scene.frame_current = self._start_frame
            self._step = 2
            print(f"← Frame zurückgesetzt auf {self._start_frame}")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Frame gesetzt. Warte eine Schleife, bevor Rückwärts-Tracking startet...")
            self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            return self.run_tracking_stability_check(context, clip)

        return {'PASS_THROUGH'}

    def run_tracking_stability_check(self, context, clip):
        current_frame = context.scene.frame_current
        current_marker_count = sum(len(track.markers) for track in clip.tracking.tracks)

        if (self._prev_marker_count == current_marker_count and
            self._prev_frame == current_frame):
            self._stable_count += 1
        else:
            self._stable_count = 0

        self._prev_marker_count = current_marker_count
        self._prev_frame = current_frame

        print(f"[Tracking-Stabilität] Frame: {current_frame}, Marker: {current_marker_count}, Stabil: {self._stable_count}/2")

        if self._stable_count >= 2:
            print("✓ Tracking stabil erkannt – gebe Fertig-Signal an Orchestrator.")
            return self._finish(context, result="FINISHED")

        return {'PASS_THROUGH'}

    def _finish(self, context, result="FINISHED"):
        # Flags für Orchestrator setzen
        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = str(result)

        self._cleanup_timer(context)
        return {'FINISHED'}

    def _cleanup_timer(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


def run_bidirectional_track(context):
    """Startet den Operator aus Skript-Kontext."""
    return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')


# ---- Registrierung für Haupt-__init__.py ----
def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
