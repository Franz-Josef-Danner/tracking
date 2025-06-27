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
) -> None:
    """Simulate one tracking cycle with adaptive thresholding."""
    print(f"Tracking gestartet bei Frame {frame_current}")
    print(
        f"Start Threshold: {config.threshold} | Threshold Marker Count: {config.threshold_marker_count}"
    )

    clip = get_movie_clip(bpy.context)
    if not clip:
        print("No active MovieClip found")
        return

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
        existing = {t.name for t in clip.tracking.tracks}
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
            if track.name not in existing and track.markers:
                placed_tracks.append(track)
                placed_markers.append(track.markers[0])
        # _validate_markers() temporarily disabled to inspect raw marker count
        # good, bad, good_tracks, bad_tracks = _validate_markers(
        #     list(zip(placed_markers, placed_tracks)),
        #     active_markers,
        #     frame_width,
        #     frame_height,
        #     config.marker_distance,
        # )

        # for track in clip.tracking.tracks:
        #     for marker in track.markers:
        #         if marker in bad:
        #             track.select = True
        #             bpy.ops.clip.delete_track()
        #             break
        # placed_tracks = good_tracks

        config.good_markers = [str(m.co.xy) for m in placed_markers]
        config.bad_markers = []
        config.placed_markers = len(placed_tracks)

        print(f"\n🟠 Iteration {threshold_iter}")
        print(f"➡️  Threshold: {config.threshold:.6f}")
        print(f"➡️  Neue Tracks erkannt: {len(placed_tracks)}")
        print(f"✅ Gesamt-Platzierte Marker: {config.placed_markers}")
        print(f"🔍 Zielbereich: {config.min_marker_range} bis {config.max_marker_range}")

        if config.min_marker_range <= config.placed_markers <= config.max_marker_range:
            print("✅ Abbruch: Zielbereich für Markeranzahl erreicht.")
            return

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
            for track in placed_tracks:
                track.select = True
                bpy.ops.clip.delete_track()
            placed_tracks.clear()
            print(
                "❌ Markeranzahl außerhalb Zielbereich, lösche alle neu gesetzten Marker dieser Iteration."
            )

        config.bad_markers.clear()
        # config.placed_markers NICHT zurücksetzen!


def get_movie_clip(context: bpy.types.Context) -> bpy.types.MovieClip | None:
    """Return the clip from the active Clip Editor if available."""

    if context.area and context.area.type == "CLIP_EDITOR":
        return context.space_data.clip

    return None


def delete_short_tracks(clip: bpy.types.MovieClip, min_track_length: int) -> None:
    """Remove tracks from *clip* shorter than *min_track_length*."""

    for track in list(clip.tracking.tracks):
        tracked_frames = sum(1 for m in track.markers if not m.mute)
        if tracked_frames < min_track_length:
            track.select = True
            bpy.ops.clip.delete_track()


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
        clip = get_movie_clip(context)
        active_markers = (
            get_active_marker_positions(clip, context.scene.frame_current)
            if clip
            else []
        )

        run_tracking_cycle(
            config,
            active_markers=active_markers,
            frame_current=context.scene.frame_current,
        )

        clip = get_movie_clip(context)
        if clip:
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

if __name__ == "__main__":
    scene = bpy.context.scene
    scene.frame_current = scene.frame_start
    scene.motion_model = MOTION_MODELS[0]
    scene.threshold = 1.0
    scene.min_marker_count = 8
    scene.min_track_length = 6

    if get_movie_clip(bpy.context):
        bpy.ops.scene.run_auto_tracking()
    else:
        print("No active MovieClip found, skipping automatic run")







