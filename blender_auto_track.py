import bpy
from bpy.props import IntProperty, StringProperty, FloatProperty
import re
import unicodedata
from dataclasses import dataclass, field
import json
import datetime

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
            "Perspective",
        ]
    )
    threshold: float = 1.0
    feature_detection: bool = True
    placed_markers: int = 0
    trigger_tracker: bool = False
    marker_track_length: dict[str, int] = field(default_factory=dict)
    max_threshold_iteration: int = 100
    max_total_iteration: int = 1000
    start_frame: int = 0
    scene_time: int = 0
    active_markers: int = 0
    abort_frame: int | None = None
    session_path: str = ""

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


def clean_name(name: str) -> str:
    """Return a normalized version of *name* for consistent comparisons.

    The name is converted to lowercase, stripped of surrounding whitespace,
    diacritics are removed and internal whitespace is collapsed.
    """

    # Normalize unicode representation and strip accents
    name_norm = unicodedata.normalize("NFKD", name)
    name_ascii = "".join(c for c in name_norm if not unicodedata.combining(c))
    # Collapse whitespace and convert to lowercase
    name_ascii = re.sub(r"\s+", " ", name_ascii).strip().casefold()
    return name_ascii


def init_session_path() -> str:
    """Return an absolute path for storing session data."""
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return bpy.path.abspath(f"//trackingsession_{ts}.json")


def save_session(config: TrackingConfig, success: bool) -> None:
    """Write tracking session information to ``config.session_path``."""
    data = {
        "start_frame": config.start_frame,
        "threshold": config.threshold,
        "min_marker_count": config.min_marker_count,
        "min_track_length": config.min_track_length,
        "threshold_marker_count": config.threshold_marker_count,
        "threshold_marker_count_plus": config.threshold_marker_count_plus,
        "motion_models": config.motion_models,
        "good_markers": config.good_markers,
        "bad_markers": config.bad_markers,
        "tracking_success": success,
        "placed_markers": config.placed_markers,
        "max_threshold_iteration": config.max_threshold_iteration,
        "max_total_iteration": config.max_total_iteration,
        "scene_time": config.scene_time,
        "active_markers": config.active_markers,
        "marker_track_length": config.marker_track_length,
        "abort_frame": config.abort_frame,
    }

    path = config.session_path or init_session_path()
    config.session_path = path
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4)
    except Exception as exc:
        pass




def _validate_markers(
    placed: list[tuple[bpy.types.MovieTrackingMarker, bpy.types.MovieTrackingTrack]],
    active: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
    distance_threshold: float,
    existing: set[str] | None = None,
) -> tuple[
    list[bpy.types.MovieTrackingMarker],
    list[bpy.types.MovieTrackingMarker],
    list[bpy.types.MovieTrackingTrack],
    list[bpy.types.MovieTrackingTrack],
]:
    """Validate marker positions and return lists for good and bad markers.

    If ``existing`` is provided, tracks with names in this set are ignored so
    that only newly placed markers are evaluated.
    """

    good_markers: list[bpy.types.MovieTrackingMarker] = []
    bad_markers: list[bpy.types.MovieTrackingMarker] = []
    good_tracks: list[bpy.types.MovieTrackingTrack] = []
    bad_tracks: list[bpy.types.MovieTrackingTrack] = []

    for marker, track in placed:
        if existing and track.name in existing:
            continue
        pos = (marker.co[0] * frame_width, marker.co[1] * frame_height)
        if not (0 <= pos[0] <= frame_width and 0 <= pos[1] <= frame_height):
            continue

        too_close = any(_distance(pos, a) < distance_threshold for a in active)
        if too_close:
            bad_markers.append(marker)
            bad_tracks.append(track)
        else:
            good_markers.append(marker)
            good_tracks.append(track)

    return good_markers, bad_markers, good_tracks, bad_tracks


def run_tracking_cycle(
    config: TrackingConfig,
    active_markers: list[tuple[float, float]],
    frame_width: int | None = None,
    frame_height: int | None = None,
    frame_current: int = 0,
) -> int | None:
    """Simulate one tracking cycle with adaptive thresholding.

    Returns the first frame with insufficient markers after short track
    evaluation or ``None`` if no such frame exists.
    """

    clip = get_movie_clip(bpy.context)
    if not clip:
        return None

    # Ensure the clip uses the current scene motion model for tracking
    motion_model = getattr(bpy.context.scene, "motion_model", MOTION_MODELS[0])
    clip.tracking.settings.default_motion_model = motion_model

    config.start_frame = frame_current

    if frame_width is None or frame_height is None:
        width, height = clip.size
        if frame_width is None:
            frame_width = int(width)
        if frame_height is None:
            frame_height = int(height)

    threshold_iter = 0
    while True:
        existing = set()
        for t in clip.tracking.tracks:
            try:
                existing.add(t.name)
            except Exception as exc:
                pass
        for area in bpy.context.window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                override = bpy.context.copy()
                override['area'] = area
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override['region'] = region  # Wichtig: Region muss gesetzt sein
                        break
                with bpy.context.temp_override(**override):
                    bpy.ops.clip.select_all(action='DESELECT')
                    print(
                        f"[AutoTrack] Detecting features with threshold {config.threshold:.4f}"
                    )
                    bpy.ops.clip.detect_features(threshold=config.threshold)
                break
        placed_tracks = []
        placed_markers = []
        for track in clip.tracking.tracks:
            try:
                t_name = track.name
            except Exception as exc:
                pass
                continue
            if t_name not in existing and track.markers:
                placed_tracks.append(track)
                placed_markers.append(track.markers[0])
                m_co = track.markers[0].co
                print(
                    f"[AutoTrack] New track '{t_name}' at {m_co[0]:.4f}, {m_co[1]:.4f}"
                )

        good, bad, good_tracks, bad_tracks = _validate_markers(
            list(zip(placed_markers, placed_tracks)),
            active_markers,
            frame_width,
            frame_height,
            config.marker_distance,
            existing,
        )

        print(
            f"[AutoTrack] Valid markers: {len(good)}, Rejected markers: {len(bad)}"
        )

        if bad_tracks:
            remove_tracks(clip, bad_tracks)
            print(f"[AutoTrack] Removed {len(bad_tracks)} tracks due to proximity")

        placed_tracks = good_tracks
        placed_markers = [t.markers[0] for t in good_tracks if t.markers]

        config.good_markers = [str(m.co.xy) for m in good]
        config.bad_markers = [str(m.co.xy) for m in bad]
        config.placed_markers = len(placed_tracks)

        # Adjust target marker count dynamically based on valid results
        config.threshold_marker_count = max(config.placed_markers * 2, 1)

        print(
            f"[AutoTrack] Accepted markers: {config.placed_markers}, New threshold target: {config.threshold_marker_count}"
        )

        if config.min_marker_range <= config.placed_markers <= config.max_marker_range:

            for area in bpy.context.window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    override = bpy.context.copy()
                    override['area'] = area
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override['region'] = region
                            break
                    with bpy.context.temp_override(**override):
                        bpy.ops.clip.select_all(action='SELECT')
                        bpy.ops.clip.track_markers(backwards=False, sequence=True)
                    break
            delete_short_tracks(clip, config.min_track_length, config)
            return find_first_insufficient_frame(
                clip, config.min_marker_count
            )

        if threshold_iter >= config.max_threshold_iteration:
            break

        old_threshold = config.threshold
        config.threshold = config.threshold * (
            (config.placed_markers + 0.1) / config.threshold_marker_count
        )

        print(
            f"[AutoTrack] Adjust threshold {old_threshold:.4f} -> {config.threshold:.4f}"
        )


        threshold_iter += 1
        clip = get_movie_clip(bpy.context)

        # Lösche Marker nur, wenn eine weitere Iteration folgt und Zielbereich noch nicht erreicht ist
        continue_iterations = threshold_iter < config.max_threshold_iteration
        if continue_iterations and not (
            config.min_marker_range <= config.placed_markers <= config.max_marker_range
        ):
            try:
                remove_tracks(clip, placed_tracks)
                print(
                    f"[AutoTrack] Cleared {len(placed_tracks)} temporary tracks for next iteration"
                )
            except Exception as exc:
                pass
            placed_tracks.clear()

        config.bad_markers.clear()
        # config.placed_markers NICHT zurücksetzen!

    return None


def get_movie_clip(context: bpy.types.Context) -> bpy.types.MovieClip | None:
    """Return the clip from the active Clip Editor if available."""

    if context.area and context.area.type == "CLIP_EDITOR":
        return context.space_data.clip

    return None


def remove_tracks(
    clip: bpy.types.MovieClip,
    tracks: list[bpy.types.MovieTrackingTrack],
) -> None:
    """Delete *tracks* from *clip* using Blender operators."""

    if not tracks:
        return

    for area in bpy.context.window.screen.areas:
        if area.type == "CLIP_EDITOR":
            override = bpy.context.copy()
            override["area"] = area
            for region in area.regions:
                if region.type == "WINDOW":
                    override["region"] = region
                    break
            with bpy.context.temp_override(**override):
                bpy.ops.clip.select_all(action="DESELECT")
                for t in tracks:
                    t.select = True
                bpy.ops.clip.delete_track()
            break


def delete_short_tracks(
    clip: bpy.types.MovieClip,
    min_track_length: int,
    config: TrackingConfig | None = None,
) -> None:
    """Remove tracks from *clip* shorter than *min_track_length*.

    If *config* is provided, store track lengths and categorize tracks as good
    or bad in the config instance before deletion.
    """

    if config is not None:
        config.good_markers.clear()
        config.bad_markers.clear()
        config.marker_track_length.clear()

    for track in list(clip.tracking.tracks):
        tracked_frames = sum(1 for m in track.markers if not m.mute)
        try:
            name = track.name
        except Exception as exc:
            continue
        name_clean = clean_name(name)
        if config is not None:
            config.marker_track_length[name_clean] = tracked_frames
            if tracked_frames < min_track_length:
                config.bad_markers.append(name_clean)
            else:
                config.good_markers.append(name_clean)

        if tracked_frames < min_track_length:
            try:
                remove_tracks(clip, [track])
            except Exception as exc:
                pass


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


def get_active_marker_positions(
    clip: bpy.types.MovieClip, frame: int
) -> list[tuple[float, float]]:
    """Liefert Positionen aller Marker, die im gegebenen Frame aktiv sind."""
    positions: list[tuple[float, float]] = []
    width, height = clip.size
    for track in clip.tracking.tracks:
        for marker in track.markers:
            if marker.frame == frame and not marker.mute:
                pos = (marker.co[0] * width, marker.co[1] * height)
                positions.append(pos)
                break  # Nur ein Marker pro Track
    return positions


def get_active_marker_tracks(
    clip: bpy.types.MovieClip, frame: int
) -> list[bpy.types.MovieTrackingTrack]:
    """Return tracks that have an active marker in *frame*."""
    tracks: list[bpy.types.MovieTrackingTrack] = []
    for track in clip.tracking.tracks:
        for marker in track.markers:
            if marker.frame == frame and not marker.mute:
                tracks.append(track)
                break
    return tracks


def average_marker_motion(
    clip: bpy.types.MovieClip, frame: int, n_frames: int
) -> float:
    """Return average marker motion over ``n_frames`` starting at ``frame``."""

    if n_frames < 2:
        return 0.0

    width, height = clip.size
    tracks = get_active_marker_tracks(clip, frame)
    if not tracks:
        return 0.0

    total_distance = 0.0
    for track in tracks:
        for i in range(n_frames - 1):
            f1 = frame + i
            f2 = f1 + 1
            m1 = next((m for m in track.markers if m.frame == f1 and not m.mute), None)
            m2 = next((m for m in track.markers if m.frame == f2 and not m.mute), None)
            if m1 and m2:
                p1 = (m1.co[0] * width, m1.co[1] * height)
                p2 = (m2.co[0] * width, m2.co[1] * height)
                total_distance += _distance(p1, p2)

    average_motion = total_distance / (len(tracks) * (n_frames - 1))
    return average_motion


def update_search_size_from_motion(
    context: bpy.types.Context,
    n_frames: int = 5,
    scaling_factor: float = 1.0,
    search_min: int = 50,
    search_max: int = 120,
    pattern_ratio: float = 0.5,
    pattern_min: int = 30,
) -> float:
    """Update ``search_size`` and ``pattern_size`` based on recent marker motion."""

    clip = get_movie_clip(context)
    if not clip:
        return 0.0

    frame = context.scene.frame_current
    avg_motion = average_marker_motion(clip, frame, n_frames)

    # Multiply the computed result by two so the derived pattern size is not
    # excessively small when using a 50% ratio.
    search_size = avg_motion * scaling_factor * 2
    search_size = max(search_min, min(search_size, search_max))
    search_size = int(search_size)

    pattern_size = int(search_size * pattern_ratio)
    pattern_size = max(pattern_min, min(pattern_size, search_size))

    if search_size < 2 * pattern_size:
        search_size = 2 * pattern_size
        search_size = max(search_min, min(search_size, search_max))
        pattern_size = int(search_size * pattern_ratio)
        pattern_size = max(pattern_min, min(pattern_size, search_size))

    # Store sizes on the clip's default tracking settings so that new markers
    # inherit them. Blender exposes these as ``default_search_size`` and
    # ``default_pattern_size`` directly on ``tracking.settings``.
    clip.tracking.settings.default_search_size = search_size
    clip.tracking.settings.default_pattern_size = pattern_size



    return search_size


def trigger_tracker(context: bpy.types.Context | None = None) -> TrackingConfig:
    """Trigger automatic tracking using current scene settings.

    Returns the :class:`TrackingConfig` used for this tracking run so that
    callers can inspect information such as ``active_markers``.
    """

    if context is None:
        context = bpy.context

    scene = context.scene
    config = TrackingConfig(
        min_marker_count=getattr(scene, "min_marker_count", 8),
        min_track_length=getattr(scene, "min_track_length", 6),
    )
    config.session_path = init_session_path()

    # ------------------------
    # Playhead-based handling
    # ------------------------
    if scene.frame_current == scene.frame_start:
        # Increase allowed marker count range and rotate motion model
        config.threshold_marker_count_plus += 10
        try:
            idx = MOTION_MODELS.index(scene.motion_model)
        except ValueError:
            idx = 0
        scene.motion_model = MOTION_MODELS[(idx + 1) % len(MOTION_MODELS)]
    elif scene.frame_current > scene.frame_start:
        if config.threshold_marker_count_plus > config.threshold_marker_count:
            config.threshold_marker_count_plus -= 10
            scene.motion_model = MOTION_MODELS[0]

    config.min_marker_range = int(config.threshold_marker_count_plus * 0.8)
    config.max_marker_range = int(config.threshold_marker_count_plus * 1.2)

    clip = get_movie_clip(context)
    if clip:
        if scene.frame_current > scene.frame_start:
            update_search_size_from_motion(context)
        active_markers = get_active_marker_positions(clip, scene.frame_current)
    else:
        active_markers = []

    frame = run_tracking_cycle(
        config,
        active_markers=active_markers,
        frame_current=scene.frame_current,
    )
    if frame is not None:
        context.scene.frame_current = frame
        config.abort_frame = frame
    else:
        config.abort_frame = None

    # Update the number of active markers after the tracking cycle
    clip = get_movie_clip(context)
    if clip:
        config.active_markers = len(get_active_marker_positions(clip, scene.frame_current))
    else:
        config.active_markers = 0

    save_session(config, frame is None)

    return config
# -----------------------------------------------------------------------------
# Blender operators for setup and running the tracking cycle
# -----------------------------------------------------------------------------

MOTION_MODELS = [
    "LocRotScale",
    "Affine",
    "Perspective",
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
        clip = get_movie_clip(context)
        if clip:
            clip.tracking.settings.default_search_size = 100
            clip.tracking.settings.default_pattern_size = 50
        self.report({'INFO'}, "Auto tracking initialized")
        return {'FINISHED'}


class OT_RunAutoTracking(bpy.types.Operator):
    """Run automatic tracking with up to five attempts."""

    bl_idname = "scene.run_auto_tracking"
    bl_label = "Run Auto Tracking"

    def execute(self, context):
        same_frame_attempts = 0
        last_abort = None
        while same_frame_attempts < 20:
            cfg = trigger_tracker(context)
            if cfg.active_markers >= cfg.min_marker_count:
                break

            abort_frame = cfg.abort_frame
            if abort_frame is None:
                break
            if last_abort is not None and abort_frame == last_abort:
                same_frame_attempts += 1
            else:
                same_frame_attempts = 0
            last_abort = abort_frame

            if same_frame_attempts >= 20:
                break

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



if __name__ == "__main__":
    # Only register the operators and menu when running the script directly.
    # Automatic tracking should not start immediately.
    register()






