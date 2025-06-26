import bpy
from bpy.props import IntProperty, StringProperty, FloatProperty
from dataclasses import dataclass, field

# -----------------------------------------------------------------------------
# Configuration dataclass and tracking helpers (adapted from autoTrack.py)
# -----------------------------------------------------------------------------

@dataclass
class TrackingConfig:
    """Configuration values for automatic tracking."""

    min_marker_count: int = 8
    min_track_length: int = 6
    threshold_variability: int = 0
    resolution_x: int = 1920

    good_markers: list[str] = field(default_factory=list)
    bad_markers: list[str] = field(default_factory=list)
    motion_models: list[str] = field(
        default_factory=lambda: [
            "LocRotScale",
            "Affine",
            "Loc",
            "Perspective",
            "LocRot",
        ]
    )
    threshold: float = 0.1
    feature_detection: bool = True
    placed_markers: int = 0
    trigger_tracker: bool = False
    marker_track_length: int = 0
    max_threshold_iteration: int = 100
    max_total_iteration: int = 1000
    start_frame: int = 0
    scene_time: int = 0
    active_markers: int = 0

    def __post_init__(self) -> None:
        # Derived values
        self.threshold_marker_count = self.min_marker_count * 4
        self.threshold_marker_count_plus = (
            self.threshold_marker_count + self.threshold_variability
        )
        self.min_marker_range = int(self.threshold_marker_count_plus * 0.8)
        self.max_marker_range = int(self.threshold_marker_count_plus * 1.2)
        self.marker_distance = self.resolution_x / 20
        self.marker_margin = self.resolution_x / 200


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return Euclidean distance between two points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def detect_features() -> list[tuple[float, float]]:
    """Dummy feature detection returning sample marker positions."""
    # In a real application this would run Blender's feature detection.
    return [
        (100.0, 100.0),
        (150.0, 150.0),
        (500.0, 500.0),
        (2000.0, 50.0),  # intentionally outside the default 1920 width
    ]


def _validate_markers(
    markers: list[tuple[float, float]],
    active: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
    distance_threshold: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Validate marker positions and return good and bad lists."""

    good: list[tuple[float, float]] = []
    bad: list[tuple[float, float]] = []

    for m in markers:
        if not (0 <= m[0] <= frame_width and 0 <= m[1] <= frame_height):
            continue

        too_close = any(_distance(m, a) < distance_threshold for a in active)
        if too_close:
            bad.append(m)
        else:
            good.append(m)

    return good, bad


def run_tracking_cycle(
    config: TrackingConfig,
    active_markers: list[tuple[float, float]],
    frame_width: int = 1920,
    frame_height: int = 1080,
    frame_current: int = 0,
) -> None:
    """Simulate one tracking cycle with adaptive thresholding."""
    print(f"Tracking gestartet bei Frame {frame_current}")

    config.start_frame = frame_current

    threshold_iter = 0
    while True:
        placed_markers = detect_features()
        good, bad = _validate_markers(
            placed_markers,
            active_markers,
            frame_width,
            frame_height,
            config.marker_distance,
        )

        config.good_markers = [str(m) for m in good]
        config.bad_markers = [str(m) for m in bad]
        config.placed_markers = len(good)

        print(
            f"Iteration {threshold_iter}: {config.placed_markers} Marker gefunden"
        )

        if (
            config.min_marker_range <= config.placed_markers <= config.max_marker_range
            or threshold_iter >= config.max_threshold_iteration
        ):
            print("Tracking beendet")
            break

        config.threshold = config.threshold / (
            config.threshold_marker_count / (config.placed_markers + 0.1)
        )

        print(f"Neuer Threshold: {config.threshold}")

        threshold_iter += 1
        config.bad_markers.clear()
        config.placed_markers = 0


def get_movie_clip(context: bpy.types.Context) -> bpy.types.MovieClip | None:
    """Return the active MovieClip if available."""

    if context.space_data and context.space_data.type == "CLIP_EDITOR":
        return context.space_data.clip

    return getattr(context.scene, "clip", None)


def delete_short_tracks(clip: bpy.types.MovieClip, min_track_length: int) -> None:
    """Remove tracks from *clip* shorter than *min_track_length*."""

    for track in list(clip.tracking.tracks):
        tracked_frames = sum(1 for m in track.markers if not m.mute)
        if tracked_frames < min_track_length:
            clip.tracking.tracks.remove(track)


def find_first_insufficient_frame(
    clip: bpy.types.MovieClip, min_marker_count: int
) -> int | None:
    """Return the first frame with fewer active markers than required."""

    frame_start = clip.frame_start
    frame_end = clip.frame_duration

    for frame in range(frame_start, frame_end):
        active_marker_count = 0
        for track in clip.tracking.tracks:
            if any(m.frame == frame and not m.mute for m in track.markers):
                active_marker_count += 1
        if active_marker_count < min_marker_count:
            return frame

    return None


# -----------------------------------------------------------------------------
# Blender operators for setup and running the tracking cycle
# -----------------------------------------------------------------------------

MOTION_MODELS = [
    "LocRotScale",
    "Affine",
    "Loc",
    "Perspective",
    "LocRot",
]


class OT_SetupAutoTracking(bpy.types.Operator):
    """Set up scene for auto tracking."""

    bl_idname = "scene.setup_auto_tracking"
    bl_label = "Setup Auto Tracking"

    min_marker_count: IntProperty(name="Min Marker Count", default=8)
    min_track_length: IntProperty(name="Min Track Length", default=6)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        scene.frame_current = scene.frame_start
        scene.motion_model = MOTION_MODELS[0]
        scene.threshold = 1.0
        scene.min_marker_count = self.min_marker_count
        scene.min_track_length = self.min_track_length
        self.report({'INFO'}, "Auto tracking initialized")
        return {'FINISHED'}


class OT_RunAutoTracking(bpy.types.Operator):
    """Run a single automatic tracking cycle."""

    bl_idname = "scene.run_auto_tracking"
    bl_label = "Run Auto Tracking"

    def execute(self, context):
        config = TrackingConfig(
            min_marker_count=context.scene.min_marker_count,
            min_track_length=context.scene.min_track_length,
        )
        run_tracking_cycle(
            config,
            active_markers=[(50.0, 50.0), (400.0, 400.0)],
            frame_current=context.scene.frame_current,
        )

        clip = get_movie_clip(context)
        if clip:
            delete_short_tracks(clip, config.min_track_length)
            frame = find_first_insufficient_frame(clip, config.min_marker_count)
            if frame is not None:
                self.report({'INFO'}, f"Insufficient markers at frame {frame}")

        self.report({'INFO'}, "Auto tracking cycle executed")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Registration helpers
# -----------------------------------------------------------------------------

def register() -> None:
    bpy.types.Scene.motion_model = StringProperty()
    bpy.types.Scene.threshold = FloatProperty()
    bpy.types.Scene.min_marker_count = IntProperty()
    bpy.types.Scene.min_track_length = IntProperty()
    bpy.utils.register_class(OT_SetupAutoTracking)
    bpy.utils.register_class(OT_RunAutoTracking)


def unregister() -> None:
    bpy.utils.unregister_class(OT_SetupAutoTracking)
    bpy.utils.unregister_class(OT_RunAutoTracking)
    del bpy.types.Scene.motion_model
    del bpy.types.Scene.threshold
    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_track_length


if __name__ == "__main__":
    register()
