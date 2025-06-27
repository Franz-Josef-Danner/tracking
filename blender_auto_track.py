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
            "Loc",
            "Perspective",
            "LocRot",
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
    }

    path = config.session_path or init_session_path()
    config.session_path = path
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4)
        print(f"Session gespeichert: {path}")
    except Exception as exc:
        print(f"⚠️ Fehler beim Speichern der Session: {exc}")




def _validate_markers(
    placed: list[tuple[bpy.types.MovieTrackingMarker, bpy.types.MovieTrackingTrack]],
    active: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
    distance_threshold: float,
) -> tuple[
    list[bpy.types.MovieTrackingMarker],
    list[bpy.types.MovieTrackingMarker],
    list[bpy.types.MovieTrackingTrack],
    list[bpy.types.MovieTrackingTrack],
]:
    """Validate marker positions and return lists for good and bad markers."""

    good_markers: list[bpy.types.MovieTrackingMarker] = []
    bad_markers: list[bpy.types.MovieTrackingMarker] = []
    good_tracks: list[bpy.types.MovieTrackingTrack] = []
    bad_tracks: list[bpy.types.MovieTrackingTrack] = []

    for marker, track in placed:
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
    print(f"Tracking gestartet bei Frame {frame_current}")
    print(
        f"Start Threshold: {config.threshold} | Threshold Marker Count: {config.threshold_marker_count}"
    )

    clip = get_movie_clip(bpy.context)
    if not clip:
        print("No active MovieClip found")
        return None

    # Ensure the clip uses the current scene motion model for tracking
    motion_model = getattr(bpy.context.scene, "motion_model", MOTION_MODELS[0])
    clip.tracking.settings.default_motion_model = motion_model
    print(f"\n🔧 Motion Model gesetzt auf: {motion_model}")

    print(
        f"🎬 Clip: {clip.name}, Frame-Bereich: {clip.frame_start}-{clip.frame_duration}"
    )

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
                print(f'⚠️ Fehler beim Lesen des Track-Namens: {exc}')
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
                    bpy.ops.clip.detect_features(threshold=config.threshold)
                break
        placed_tracks = []
        placed_markers = []
        for track in clip.tracking.tracks:
            try:
                t_name = track.name
            except Exception as exc:
                print(f'⚠️ Fehler beim Lesen des Track-Namens: {exc}')
                continue
            if t_name not in existing and track.markers:
                placed_tracks.append(track)
                placed_markers.append(track.markers[0])

        good, bad, good_tracks, bad_tracks = _validate_markers(
            list(zip(placed_markers, placed_tracks)),
            active_markers,
            frame_width,
            frame_height,
            config.marker_distance,
        )

        print(
            f"🔍 Validierte Marker: {len(good_tracks)} / {len(placed_tracks)} ursprünglich"
        )

        for track in clip.tracking.tracks:
            for marker in track.markers:
                if marker in bad:
                    track.select = True
                    bpy.ops.clip.delete_track()
                    break

        placed_tracks = good_tracks
        placed_markers = [t.markers[0] for t in good_tracks if t.markers]

        config.good_markers = [str(m.co.xy) for m in good]
        config.bad_markers = [str(m.co.xy) for m in bad]
        config.placed_markers = len(placed_tracks)

        print(f"\n🟠 Iteration {threshold_iter}")
        print(f"➡️  Threshold: {config.threshold:.6f}")
        print(f"➡️  Neue Tracks erkannt: {len(placed_tracks)}")
        print(f"✅ Gesamt-Platzierte Marker: {config.placed_markers}")
        print(f"🔍 Zielbereich: {config.min_marker_range} bis {config.max_marker_range}")

        if config.min_marker_range <= config.placed_markers <= config.max_marker_range:
            print("✅ Abbruch: Zielbereich für Markeranzahl erreicht.")

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
            print("⛔️ Abbruch: Maximale Anzahl an Threshold-Iterationen erreicht.")
            break

        old_threshold = config.threshold
        config.threshold = config.threshold * (
            (config.placed_markers + 0.1) / config.threshold_marker_count
        )

        print(f"📉 Neuer Threshold berechnet: {old_threshold:.6f} → {config.threshold:.6f}")

        threshold_iter += 1
        clip = get_movie_clip(bpy.context)

        # Lösche Marker nur, wenn eine weitere Iteration folgt und Zielbereich noch nicht erreicht ist
        continue_iterations = threshold_iter < config.max_threshold_iteration
        if continue_iterations and not (
            config.min_marker_range <= config.placed_markers <= config.max_marker_range
        ):
            try:
                remove_tracks(clip, placed_tracks)
            except Exception as exc:
                print(f'⚠️ Fehler beim Entfernen des Tracks: {exc}')
            placed_tracks.clear()
            print(
                "❌ Markeranzahl außerhalb Zielbereich, lösche alle neu gesetzten Marker dieser Iteration."
            )

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
            print(f'⚠️ Fehler beim Lesen des Track-Namens: {exc}')
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
                print(f'⚠️ Fehler beim Entfernen des Tracks: {exc}')


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
    active_markers = (
        get_active_marker_positions(clip, scene.frame_current) if clip else []
    )

    frame = run_tracking_cycle(
        config,
        active_markers=active_markers,
        frame_current=scene.frame_current,
    )
    if frame is not None:
        print(f"Insufficient markers at frame {frame}")
        context.scene.frame_current = frame
        print(
            f"\u27a1\ufe0f Playhead nach Trackingende auf Frame {context.scene.frame_current} gesetzt "
            f"(Start: {config.start_frame})"
        )
    else:
        print(
            f"Tracking abgeschlossen ohne unzureichende Marker. "
            f"Playhead verbleibt auf Frame {context.scene.frame_current}"
        )

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
    """Run automatic tracking with up to five attempts."""

    bl_idname = "scene.run_auto_tracking"
    bl_label = "Run Auto Tracking"

    def execute(self, context):
        for attempt in range(5):
            cfg = trigger_tracker(context)
            if cfg.active_markers >= cfg.min_marker_count:
                break
            print(
                f"❌ Versuch {attempt + 1}: Nur {cfg.active_markers} aktive Marker, erneut versuchen"
            )
        else:
            print("⛔️ Maximale Anzahl an Versuchen erreicht")

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
    print("Auto tracking operators registered. Use the menu to start tracking.")






