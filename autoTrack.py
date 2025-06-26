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


def main() -> None:
    config = parse_args()
    print("Tracking configuration:")
    for field_name, value in config.__dict__.items():
        print(f"  {field_name}: {value}")


if __name__ == "__main__":
    main()
