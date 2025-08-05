import bpy
from bpy.types import Operator
import time


class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts mit Cleanup"

    _timer = None
    _step = 0
    _start_frame = 0
    _marker_counts = []
    _cleanup_threshold = 5  # z.B. Mindestanzahl an Frames pro Track

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
        tracking = clip.tracking
        tracks = tracking.tracks

        override = context.copy()

        if self._step == 0:
            print("→ Starte Vorwärts-Tracking...")
            bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)
            self._step += 1
            print("✓ Vorwärts-Tracking abgeschlossen.")
            context.scene.frame_current = self._start_frame  # zurücksetzen
            return {'PASS_THROUGH'}

        elif self._step == 1:
            print("→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=True, sequence=True)
            self._step += 1
            print("✓ Rückwärts-Tracking abgeschlossen.")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Starte Bereinigung kurzer Tracks...")

            short_tracks = []
            for track in tracks:
                frame_count = len([p for p in track.markers if not p.mute])
                if frame_count < self._cleanup_threshold:
                    short_tracks.append(track)

            if short_tracks:
                for t in short_tracks:
                    t.select = True
                bpy.ops.clip.delete_track()
                print(f"→ {len(short_tracks)} kurze Tracks entfernt.")
            else:
                print("→ Keine kurzen Tracks gefunden.")

            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("✓ Tracking und Cleanup abgeschlossen.")
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}
