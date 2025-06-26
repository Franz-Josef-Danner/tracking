import argparse
from dataclasses import dataclass, field

@dataclass
class TrackingConfig:
    """Configuration values for automatic tracking."""

    min_marker_count: int = 8
    min_track_length: int = 6
    threshold_variability: int = 0
    resolution_x: int = 1920

    good_markers: list[str] = field(default_factory=list)
    bad_markers: list[str] = field(default_factory=list)
    motion_models: list[str] = field(default_factory=lambda: [
        "LocRotScale",
        "Affine",
        "Loc",
        "Perspective",
        "LocRot",
    ])
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

    def __post_init__(self):
        # Derived values
        self.threshold_marker_count = self.min_marker_count * 4
        self.threshold_marker_count_plus = (
            self.threshold_marker_count + self.threshold_variability
        )
        self.min_marker_range = int(self.threshold_marker_count_plus * 0.8)
        self.max_marker_range = int(self.threshold_marker_count_plus * 1.2)
        self.marker_distance = self.resolution_x / 20
        self.marker_margin = self.resolution_x / 200


def parse_args() -> TrackingConfig:
    parser = argparse.ArgumentParser(description="Auto Tracker Settings")
    parser.add_argument(
        "--min-marker-count",
        type=int,
        default=8,
        help="Minimum number of active markers per frame",
    )
    parser.add_argument(
        "--min-track-length",
        type=int,
        default=6,
        help="Minimum frames a marker must track before it is kept",
    )
    parser.add_argument(
        "--threshold-variability",
        type=int,
        default=0,
        help="Adjustment added to the computed threshold marker count",
    )
    parser.add_argument(
        "--resolution-x",
        type=int,
        default=1920,
        help="Horizontal resolution used for computing spacing",
    )
    args = parser.parse_args()
    return TrackingConfig(
        min_marker_count=args.min_marker_count,
        min_track_length=args.min_track_length,
        threshold_variability=args.threshold_variability,
        resolution_x=args.resolution_x,
    )


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


def run_tracking_cycle(
    config: TrackingConfig,
    active_markers: list[tuple[float, float]],
    frame_width: int = 1920,
    frame_height: int = 1080,
) -> None:
    """Simulate one tracking cycle following the described algorithm."""

    # Save the playhead position as the start frame
    config.start_frame = config.scene_time

    # Trigger feature detection and store placed marker positions
    placed_markers = detect_features()
    config.placed_markers = len(placed_markers)

    # Filter markers that lie outside the frame bounds
    in_frame = [
        m
        for m in placed_markers
        if 0 <= m[0] < frame_width and 0 <= m[1] < frame_height
    ]

    good: list[tuple[float, float]] = []
    bad: list[tuple[float, float]] = []

    # Compare distance to active markers
    for m in in_frame:
        too_close = any(_distance(m, a) < config.marker_distance for a in active_markers)
        if too_close:
            bad.append(m)
        else:
            good.append(m)

    config.good_markers = [str(m) for m in good]
    config.bad_markers = [str(m) for m in bad]
    config.placed_markers = len(good)

    # Adjust threshold if placed markers are outside the allowed range
    if (
        config.placed_markers < config.min_marker_range
        or config.placed_markers > config.max_marker_range
    ):
        config.threshold = config.threshold / (
            config.threshold_marker_count / (config.placed_markers + 0.1)
        )

    # Clean up for next iteration
    config.placed_markers = 0
    config.bad_markers.clear()


def main() -> None:
    config = parse_args()
    print("Tracking configuration:")
    for field_name, value in config.__dict__.items():
        print(f"  {field_name}: {value}")

    # Example call using two active markers. In practice these would be
    # sourced from the current tracking data.
    active = [(50.0, 50.0), (400.0, 400.0)]
    run_tracking_cycle(config, active)

    print("\nConfiguration after tracking cycle:")
    for field_name, value in config.__dict__.items():
        print(f"  {field_name}: {value}")


if __name__ == "__main__":
    main()
