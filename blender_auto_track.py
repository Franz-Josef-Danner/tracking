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
    threshold: float = 1.0
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


def detect_features(
    ) -> tuple[
        list[tuple[float, float]], list[bpy.types.MovieTrackingTrack]
    ]:
    """Run Blender's feature detection on the active clip.

    Returns a tuple ``(positions, tracks)`` with the detected marker
    positions and the corresponding ``MovieTrackingTrack`` objects.
    """

    context = bpy.context
    clip = get_movie_clip(context)
    if not clip:
        print("No active MovieClip found for feature detection")
        return [], []

    existing = {t.name for t in clip.tracking.tracks}

    bpy.ops.clip.detect_features()

    width, height = clip.size
    new_positions: list[tuple[float, float]] = []
    new_tracks: list[bpy.types.MovieTrackingTrack] = []
    for track in clip.tracking.tracks:
        if track.name not in existing and track.markers:
            co = track.markers[0].co
            new_positions.append((co[0] * width, co[1] * height))
            new_tracks.append(track)

    return new_positions, new_tracks


def _validate_markers(
    placed: list[tuple[tuple[float, float], bpy.types.MovieTrackingTrack]],
    active: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
    distance_threshold: float,
) -> tuple[
    list[tuple[float, float]],
    list[tuple[float, float]],
    list[bpy.types.MovieTrackingTrack],
    list[bpy.types.MovieTrackingTrack],
]:
    """Validate marker positions and return lists for good and bad markers."""

    good_markers: list[tuple[float, float]] = []
    bad_markers: list[tuple[float, float]] = []
    good_tracks: list[bpy.types.MovieTrackingTrack] = []
    bad_tracks: list[bpy.types.MovieTrackingTrack] = []

    for pos, track in placed:
        if not (0 <= pos[0] <= frame_width and 0 <= pos[1] <= frame_height):
            continue

        too_close = any(_distance(pos, a) < distance_threshold for a in active)
        if too_close:
            bad_markers.append(pos)
            bad_tracks.append(track)
        else:
            good_markers.append(pos)
            good_tracks.append(track)

    return good_markers, bad_markers, good_tracks, bad_tracks


def run_tracking_cycle(
    config: TrackingConfig,
    active_markers: list[tuple[float, float]],
    frame_width: int | None = None,
    frame_height: int | None = None,
    frame_current: int = 0,
) -> None:
    """Simulate one tracking cycle with adaptive thresholding."""
    print(f"Tracking gestartet bei Frame {frame_current}")

    config.start_frame = frame_current

    if frame_width is None or frame_height is None:
        clip = get_movie_clip(bpy.context)
        if clip:
            width, height = clip.size
            if frame_width is None:
                frame_width = int(width)
            if frame_height is None:
                frame_height = int(height)
        else:
            frame_width = frame_width or 1920
            frame_height = frame_height or 1080

    threshold_iter = 0
    while True:
        placed_markers, placed_tracks = detect_features()
        clip = get_movie_clip(bpy.context)
        good,
        bad,
        good_tracks,
        bad_tracks = _validate_markers(
            list(zip(placed_markers, placed_tracks)),
            active_markers,
            frame_width,
            frame_height,
            config.marker_distance,
        )

        if clip:
            for track in bad_tracks:
                clip.tracking.tracks.remove(track)
        placed_tracks = good_tracks

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

        config.threshold = config.threshold * (
            (config.placed_markers + 0.1) / config.threshold_marker_count
        )

        print(f"Neuer Threshold: {config.threshold}")

        threshold_iter += 1
        clip = get_movie_clip(bpy.context)
        if clip:
            for track in placed_tracks:
                clip.tracking.tracks.remove(track)

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

def draw_func(self, context):
    """Draw menu entries for the auto tracking operators."""

    layout = self.layout
    layout.operator("scene.setup_auto_tracking")
    layout.operator("scene.run_auto_tracking")

def register() -> None:
    bpy.types.Scene.motion_model = StringProperty()
    bpy.types.Scene.threshold = FloatProperty()
    bpy.types.Scene.min_marker_count = IntProperty()
    bpy.types.Scene.min_track_length = IntProperty()
    bpy.utils.register_class(OT_SetupAutoTracking)
    bpy.utils.register_class(OT_RunAutoTracking)

    # Integrate the operators in the Clip editor menu for convenience
    bpy.types.CLIP_MT_clip.append(draw_func)


def unregister() -> None:
    bpy.utils.unregister_class(OT_SetupAutoTracking)
    bpy.utils.unregister_class(OT_RunAutoTracking)
    del bpy.types.Scene.motion_model
    del bpy.types.Scene.threshold
    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_track_length

    bpy.types.CLIP_MT_clip.remove(draw_func)


register()
