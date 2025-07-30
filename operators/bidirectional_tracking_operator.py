import bpy
from ..helpers.invoke_clip_operator_safely import invoke_clip_operator_safely


class TrackingController:
    """State-based bidirectional tracking controller."""

    def __init__(self, context: bpy.types.Context):
        self.context = context
        self.clip = context.space_data.clip
        self.tracking = self.clip.tracking
        self.step = 0  # 0 = forward, 1 = wait, 2 = backward, 3 = wait, 4 = cleanup
        self.prev_frame = context.scene.frame_current
        self.frame_stable_counter = 0
        self.marker_counts_prev = [len(t.markers) for t in self.tracking.tracks]
        self.tracking_done_delay = 0

        print("Bidirektionales Tracking initialisiert.")

    def is_tracking_done_robust(self) -> bool:
        current_frame = self.context.scene.frame_current
        same_frame = current_frame == self.prev_frame

        if same_frame:
            self.frame_stable_counter += 1
        else:
            self.frame_stable_counter = 0

        self.prev_frame = current_frame

        marker_counts_now = [len(t.markers) for t in self.tracking.tracks]
        new_markers = any(now > prev for now, prev in zip(marker_counts_now, self.marker_counts_prev))
        self.marker_counts_prev = marker_counts_now

        if new_markers:
            self.tracking_done_delay = 0
            return False

        if self.frame_stable_counter >= 3:
            self.tracking_done_delay += 1
            if self.tracking_done_delay >= 3:
                return True

        return False

    def run(self):
        print(f"[Tracking] Schritt: {self.step}")
        if self.step == 0:
            print("→ Starte Vorwärts-Tracking...")
            invoke_clip_operator_safely("track_markers", backwards=False, sequence=True)
            self.step = 1
        elif self.step == 1:
            print("→ Warte auf Abschluss des Vorwärts-Trackings...")
            if self.is_tracking_done_robust():
                print("✓ Vorwärts-Tracking abgeschlossen.")
                self.step = 2
        elif self.step == 2:
            print("→ Starte Rückwärts-Tracking...")
            invoke_clip_operator_safely("track_markers", backwards=True, sequence=True)
            self.step = 3
        elif self.step == 3:
            print("→ Warte auf Abschluss des Rückwärts-Trackings...")
            if self.is_tracking_done_robust():
                print("✓ Rückwärts-Tracking abgeschlossen.")
                self.step = 4
        elif self.step == 4:
            print("→ Starte Bereinigung kurzer Tracks...")
            self.cleanup_short_tracks()
            print("✓ Tracking und Cleanup abgeschlossen.")
            return None
        return 0.5

    def cleanup_short_tracks(self) -> None:
        scene = self.context.scene
        min_length = scene.get("frames_per_track", 10)

        print(f"Starte automatische Bereinigung mit clean_tracks (Frames < {min_length})…")
        bpy.ops.clip.clean_tracks(frames=min_length, error=0.0, action='DELETE_TRACK')
        print(f"✓ Alle Tracks mit weniger als {min_length} Frames wurden entfernt.")


_tracking_controller = None

def start_bidirectional_tracking(context: bpy.types.Context) -> None:
    global _tracking_controller
    _tracking_controller = TrackingController(context)
    bpy.app.timers.register(_tracking_controller.run, first_interval=0.5)
    print("Timer für bidirektionales Tracking gestartet.")


class TRACKING_OT_bidirectional_tracking(bpy.types.Operator):
    bl_idname = "tracking.bidirectional_tracking"
    bl_label = "Tracking"
    bl_description = (
        "Bidirektionales Tracking aller selektierten Marker mit Löschung kurzer Tracks"
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            print("⚠ Kein Clip geladen.")
            return {'CANCELLED'}

        if not clip.use_proxy:
            clip.use_proxy = True
            print("Proxy-Generierung aktiviert.")

        print("Tracking wird gestartet...")
        start_bidirectional_tracking(context)
        return {'FINISHED'}
