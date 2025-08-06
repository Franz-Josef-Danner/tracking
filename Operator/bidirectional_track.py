import bpy
from bpy.types import Operator
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame

class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts"

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    def execute(self, context):
        self._step = 0
        self._start_frame = context.scene.frame_current
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
            context.scene.frame_current = self._start_frame
            self._step += 1
            print(f"← Frame zurückgesetzt auf {self._start_frame}")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Frame wurde gesetzt. Warte eine Schleife ab, bevor Tracking startet...")
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 4:
            return self.run_tracking_stability_check(context)

        return {'PASS_THROUGH'}

    def run_tracking_stability_check(self, context):
        clip = context.space_data.clip
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
            print("✓ Tracking stabil erkannt – bereinige kurze Tracks.")
            bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')

            # ➕ Zusätzlicher Ablauf nach Abschluss:
            scene = context.scene
            min_marker = scene.get("min_marker", 5)

            low_frame = find_low_marker_frame(clip, min_marker=min_marker)
            if low_frame is not None:
                jump_to_frame(context, frame_number=low_frame)
            else:
                print("→ Kein Frame mit zu wenigen Markern gefunden. Kein Sprung notwendig.")

            context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}
