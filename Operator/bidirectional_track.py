import bpy
import time

class CLIP_OT_smart_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.smart_bidirectional_track"
    bl_label = "Smart Bidirectional Track"
    bl_description = "Trackt vorwärts, prüft Stillstand und trackt rückwärts"

    _last_marker_count = 0
    _last_frame = 0
    _no_change_count = 0
    _start_time = 0
    _direction = 'FORWARD'

    @classmethod
    def poll(cls, context):
        return context.space_data.clip is not None

    def execute(self, context):
        self._direction = 'FORWARD'
        self._start_time = time.time()
        self._last_marker_count = self._count_markers(context)
        self._last_frame = context.scene.frame_current
        self._no_change_count = 0

        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

        bpy.app.timers.register(lambda: self._monitor_tracking(context), first_interval=0.5)
        return {'FINISHED'}

    def _count_markers(self, context):
        count = 0
        for track in context.space_data.clip.tracking.tracks:
            if track.select:
                count += len([m for m in track.markers if not m.mute])
        return count

    def _monitor_tracking(self, context):
        current_marker_count = self._count_markers(context)
        current_frame = context.scene.frame_current

        if current_marker_count == self._last_marker_count and current_frame == self._last_frame:
            self._no_change_count += 1
        else:
            self._no_change_count = 0

        self._last_marker_count = current_marker_count
        self._last_frame = current_frame

        if self._no_change_count >= 2:
            if self._direction == 'FORWARD':
                self._direction = 'BACKWARD'
                self._no_change_count = 0
                bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
                return 0.5  # erneut prüfen
            else:
                return None  # fertig

        return 0.5  # erneut prüfen
