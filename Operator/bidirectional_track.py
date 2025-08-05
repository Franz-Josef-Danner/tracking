import bpy

bl_info = {
    "name": "Bidirectional Tracker",
    "blender": (4, 4, 0),
    "category": "Clip",
}


def start_tracking(direction='FORWARDS'):
    """Starte Tracking im Clip Editor über Context Override."""
    for area in bpy.context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = {
                        'area': area,
                        'region': region,
                        'scene': bpy.context.scene,
                        'space_data': area.spaces.active
                    }
                    bpy.ops.clip.track_markers(
                        override,
                        backwards=(direction == 'BACKWARDS'),
                        sequence=True
                    )
                    return True
    print("❌ Kein CLIP_EDITOR gefunden.")
    return False


class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Selektierte Marker vorwärts und rückwärts tracken, wenn keine Bewegung mehr erkannt wird"""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirektional Tracken"
    bl_options = {'REGISTER', 'UNDO'}

    _last_marker_count = 0
    _no_change_count = 0
    _phase = 'FORWARDS'

    def execute(self, context):
        self._last_marker_count = self.count_selected_markers()
        self._no_change_count = 0
        self._phase = 'FORWARDS'
        start_tracking(direction='FORWARDS')
        bpy.app.timers.register(self.monitor_tracking, first_interval=0.5)
        return {'FINISHED'}

    def count_selected_markers(self):
        """Zähle alle selektierten Marker in der aktiven Clip"""
        count = 0
        clip = bpy.context.space_data.clip
        for track in clip.tracking.tracks:
            if track.select:
                for marker in track.markers:
                    if marker.select:
                        count += 1
        return count

    def monitor_tracking(self):
        """Überwache Tracking-Fortschritt und starte ggf. Rückwärts-Tracking"""
        current_count = self.count_selected_markers()
        if current_count == self._last_marker_count:
            self._no_change_count += 1
        else:
            self._no_change_count = 0
            self._last_marker_count = current_count

        if self._no_change_count >= 2:
            if self._phase == 'FORWARDS':
                print("➡️ Vorwärts beendet – Rückwärts starten...")
                self._phase = 'BACKWARDS'
                start_tracking(direction='BACKWARDS')
                self._no_change_count = 0
                return 0.5  # weiter beobachten
            else:
                print("✅ Rückwärts beendet – Tracking abgeschlossen.")
                return None  # Timer stoppen

        return 0.5  # weiter beobachten


def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)


if __name__ == "__main__":
    register()
