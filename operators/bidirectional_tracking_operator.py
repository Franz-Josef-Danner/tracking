import bpy
from ..helpers import invoke_clip_operator_safely


class TrackingController:
    """State-based bidirectional tracking controller."""

    def __init__(self, context: bpy.types.Context):
        self.context = context
        self.clip = context.space_data.clip
        self.tracking = self.clip.tracking
        # 0 = forward, 1 = wait, 2 = backward, 3 = wait, 4 = cleanup
        self.step = 0
        self.prev_marker_counts = self.get_marker_lengths()

    def get_marker_lengths(self) -> list[int]:
        """Return marker count per selected track."""
        return [len(t.markers) for t in self.tracking.tracks if t.select]

    def is_tracking_done(self) -> bool:
        """Check if marker counts stopped changing."""
        current_counts = self.get_marker_lengths()
        changed = current_counts != self.prev_marker_counts
        self.prev_marker_counts = current_counts
        return changed

    def run(self):
        if self.step == 0:
            invoke_clip_operator_safely(
                "track_markers",
                invoke="INVOKE_DEFAULT",
                backwards=False,
                sequence=True,
            )
            self.step = 1
        elif self.step == 1:
            if self.is_tracking_done():
                self.step = 2
        elif self.step == 2:
            invoke_clip_operator_safely(
                "track_markers",
                invoke="INVOKE_DEFAULT",
                backwards=True,
                sequence=True,
            )
            self.step = 3
        elif self.step == 3:
            if self.is_tracking_done():
                self.step = 4
        elif self.step == 4:
            self.cleanup_short_tracks()
            return None
        return 0.5

    def cleanup_short_tracks(self) -> None:
        scene = self.context.scene
        min_length = scene.get("frames_per_track", 10)
        short_tracks: list[bpy.types.MovieTrackingTrack] = []

        for track in self.tracking.tracks:
            if not track.select or all(m.mute for m in track.markers):
                continue

            frames = [m.frame for m in track.markers if not m.mute]
            if not frames:
                continue

            if (max(frames) - min(frames) + 1) < min_length:
                short_tracks.append(track)

        if short_tracks:
            for t in short_tracks:
                t.select = True
            bpy.ops.clip.delete_track()
            print(f"{len(short_tracks)} kurze Tracks gel\u00f6scht (< {min_length} Frames).")
        else:
            print("Keine kurzen Tracks gefunden.")


_tracking_controller = None


def start_bidirectional_tracking(context: bpy.types.Context) -> None:
    global _tracking_controller
    _tracking_controller = TrackingController(context)
    bpy.app.timers.register(_tracking_controller.run, first_interval=0.5)


class TRACKING_OT_bidirectional_tracking(bpy.types.Operator):
    bl_idname = "tracking.bidirectional_tracking"
    bl_label = "Tracking"
    bl_description = (
        "Bidirektionales Tracking aller selektierten Marker mit L\u00f6schung kurzer Tracks"
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
            return {'CANCELLED'}
        tracking = clip.tracking

        # 1. Proxy aktivieren
        if not clip.use_proxy:
            clip.use_proxy = True

        # 2. Bidirektionales Tracking per Timer starten
        start_bidirectional_tracking(context)

        return {'FINISHED'}
