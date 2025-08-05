import bpy

def start_tracking(direction='FORWARDS'):
    """Starte das Tracking in eine Richtung."""
    bpy.ops.clip.track_markers(
        backwards=(direction == 'BACKWARDS'),
        sequence=False
    )

class TrackingMonitor:
    """Überwacht die Anzahl Marker nach dem Vorwärts-Tracking."""
    def __init__(self, clip):
        self.clip = clip
        self.prev_marker_count = self.get_marker_count()
        self.idle_checks = 0
        self.max_idle_checks = 2  # zwei aufeinanderfolgende "Ruhe"-Checks

    def get_marker_count(self):
        return sum(
            len(track.markers)
            for track in self.clip.tracking.tracks
            if track.select
        )

    def monitor(self):
        current_count = self.get_marker_count()
        if current_count == self.prev_marker_count:
            self.idle_checks += 1
        else:
            self.idle_checks = 0

        self.prev_marker_count = current_count

        if self.idle_checks >= self.max_idle_checks:
            start_tracking(direction='BACKWARDS')
            return None  # Stoppt den Timer
        return 0.5  # Wiederhole in 0.5 Sekunden

def start_bidirectional_tracking(context):
    """Startet vorwärts und wartet auf Inaktivität, bevor rückwärts getrackt wird."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Movie Clip aktiv")
        return {'CANCELLED'}

    start_tracking(direction='FORWARDS')
    monitor = TrackingMonitor(clip)
    bpy.app.timers.register(monitor.monitor)

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Selektierte Marker vorwärts und dann rückwärts tracken"""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirektionales Tracking"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_bidirectional_tracking(context)
        return {'FINISHED'}

# Optional für direkten Test in Blender:
def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)

if __name__ == "__main__":
    register()
