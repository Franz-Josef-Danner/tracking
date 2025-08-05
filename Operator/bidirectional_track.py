import bpy
import time

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"

    _timer = None
    _step = 0
    _marker_counts = []
    _start_frame = 0
    _area_backup = None

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
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Movie Clip")
            return {'CANCELLED'}

        area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
        if not area:
            self.report({'ERROR'}, "Kein Clip Editor aktiv")
            return {'CANCELLED'}

        override = {'window': context.window, 'screen': context.screen, 'area': area, 'region': area.regions[-1]}

        if self._step == 0:
            print("→ Starte Vorwärts-Tracking...")
            bpy.ops.clip.track_markers(override, backwards=False, sequence=True)
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            if self.is_tracking_done(clip):
                print("✓ Vorwärts-Tracking abgeschlossen.")
                context.scene.frame_current = self._start_frame
                print(f"← Frame zurückgesetzt auf {self._start_frame}")
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Starte Rückwärts-Tracking...")
            bpy.ops.clip.track_markers(override, backwards=True, sequence=True)
            self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            if self.is_tracking_done(clip):
                print("✓ Rückwärts-Tracking abgeschlossen.")
                self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            print("→ Starte Bereinigung kurzer Tracks...")
            self.cleanup_short_tracks(clip)
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            print("✓ Tracking und Cleanup abgeschlossen.")
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def is_tracking_done(self, clip):
        current_count = sum(1 for track in clip.tracking.tracks if track.select)
        self._marker_counts.append(current_count)
        if len(self._marker_counts) >= 3 and len(set(self._marker_counts[-3:])) == 1:
            return True
        return False

    def cleanup_short_tracks(self, clip):
        min_length = bpy.context.scene.min_track_length if 'min_track_length' in bpy.context.scene else 5
        for track in list(clip.tracking.tracks):
            if track.select:
                segments = track.markers
                if len(segments) < min_length:
                    track.select = True
        bpy.ops.clip.delete_track()

def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)

if __name__ == "__main__":
    register()
