import bpy
from bpy.types import Operator

bl_info = {
    "name": "Bidirektionales Tracking",
    "blender": (4, 4, 0),
    "category": "Tracking",
}


def get_clip_editor_override(context):
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {
                        "window": context.window,
                        "screen": context.screen,
                        "area": area,
                        "region": region,
                        "scene": context.scene,
                        "space_data": area.spaces.active,
                    }
    return None


def count_total_markers(context):
    count = 0
    clip = context.space_data.clip if context.space_data else None
    if clip:
        for track in clip.tracking.tracks:
            count += len(track.markers)
    return count


class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Tracks selected markers forward and backward, and cleans short tracks"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _marker_check_1 = 0
    _marker_check_2 = 0

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        return self.run_tracking_step(context)

    def execute(self, context):
        self._step = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "[Tracking] Schritt: 0 → Starte Vorwärts-Tracking...")
        return {'RUNNING_MODAL'}

    def run_tracking_step(self, context):
        override = get_clip_editor_override(context)
        if not override:
            self.report({'ERROR'}, "CLIP_EDITOR Kontext nicht gefunden")
            return {'CANCELLED'}

        if self._step == 0:
            # Starte Vorwärts-Tracking
            bpy.ops.clip.track_markers(override, 'EXEC_DEFAULT', {"backwards": False, "sequence": True})
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            # Überprüfe ob sich Markeranzahl ändert
            self._marker_check_1 = count_total_markers(context)
            self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            # Nochmals zählen
            self._marker_check_2 = count_total_markers(context)
            if self._marker_check_1 == self._marker_check_2:
                # Starte Rückwärts-Tracking
                scene = context.scene
                scene.frame_current = scene.frame_start  # auf Anfang zurück
                self.report({'INFO'}, "← Frame zurückgesetzt auf {}".format(scene.frame_start))
                self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            # Rückwärts tracken
            self.report({'INFO'}, "→ Rückwärts-Tracking starten...")
            bpy.ops.clip.track_markers(override, 'EXEC_DEFAULT', {"backwards": True, "sequence": True})
            self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            # Cleanup kurze Tracks (z.B. < min_track_length)
            self.cleanup_short_tracks(context, min_length=5)
            self.report({'INFO'}, "✓ Tracking abgeschlossen.")
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cleanup_short_tracks(self, context, min_length=5):
        clip = context.space_data.clip
        if not clip:
            return

        to_delete = []
        for track in clip.tracking.tracks:
            if len(track.markers) < min_length:
                to_delete.append(track)

        for track in to_delete:
            clip.tracking.tracks.remove(track)

        self.report({'INFO'}, f"{len(to_delete)} kurze Tracks entfernt.")


def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)


if __name__ == "__main__":
    register()
