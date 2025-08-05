import bpy
import time

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Track selektierte Marker vorwärts und rückwärts"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _last_marker_count = 0
    _no_change_counter = 0
    _start_frame = 0

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
        if not area:
            self.report({'ERROR'}, "Kein Clip-Editor gefunden")
            return {'CANCELLED'}

        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if not region:
            self.report({'ERROR'}, "Keine Region im Clip-Editor gefunden")
            return {'CANCELLED'}

        space = area.spaces.active
        override = {
            'window': context.window,
            'screen': context.screen,
            'area': area,
            'region': region,
            'space_data': space,
        }

        def count_selected_markers():
            try:
                return sum(1 for track in space.clip.tracking.tracks if track.select)
            except:
                return 0

        if self._step == 0:
            print("[Tracking] Schritt: 0\n→ Starte Vorwärts-Tracking...")
            self._start_frame = context.scene.frame_current
            bpy.ops.clip.track_markers(
                override,
                **{
                    'backwards': False,
                    'sequence': True
                }
            )
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            print("[Tracking] Schritt: 1\n→ Warte auf Abschluss des Vorwärts-Trackings...")
            current_count = count_selected_markers()
            if current_count == self._last_marker_count:
                self._no_change_counter += 1
            else:
                self._no_change_counter = 0
            self._last_marker_count = current_count

            if self._no_change_counter >= 2:
                print("✓ Vorwärts-Tracking abgeschlossen.")
                context.scene.frame_current = self._start_frame
                print(f"← Frame zurückgesetzt auf {self._start_frame}")
                self._no_change_counter = 0
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("[Tracking] Schritt: 2\n→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers(
                override,
                **{
                    'backwards': True,
                    'sequence': True
                }
            )
            self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("[Tracking] Schritt: 3\n→ Warte auf Abschluss des Rückwärts-Trackings...")
            current_count = count_selected_markers()
            if current_count == self._last_marker_count:
                self._no_change_counter += 1
            else:
                self._no_change_counter = 0
            self._last_marker_count = current_count

            if self._no_change_counter >= 2:
                print("✓ Rückwärts-Tracking abgeschlossen.")
                self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            print("[Tracking] Schritt: 4\n→ Starte Bereinigung kurzer Tracks...")

            clip = space.clip
            min_track_length = 4  # Beispielwert

            for track in clip.tracking.tracks:
                frames = [marker.frame for marker in track.markers if marker.frame != -1]
                if len(frames) < min_track_length:
                    track.select = True
                else:
                    track.select = False

            bpy.ops.clip.delete_track(override)
            print("✓ Tracking und Cleanup abgeschlossen.")
            self.cancel(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

