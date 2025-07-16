"""Simple CLI debug tool for Kaiserlich Tracksycle."""

import argparse
import os
import sys
from types import SimpleNamespace
import importlib.util

# Ensure modules are importable when run directly
sys.path.insert(0, os.path.dirname(__file__))

# Provide dummy bpy module when running outside Blender
if importlib.util.find_spec("bpy") is None:  # pragma: no cover - only for environments w/o Blender
    sys.modules["bpy"] = SimpleNamespace()
else:  # pragma: no cover - Blender available
    import bpy  # type: ignore  # noqa: F401

from modules.tracking import motion_model
from modules.tracking.track_length import get_track_length
from modules.util.tracker_logger import configure_logger


def cycle_models(steps: int) -> None:
    """Cycle through motion models and print them."""
    for _ in range(steps):
        model = motion_model.next_model()
        print(model)


def show_track_length(frames):
    """Display the length of a dummy track."""
    class DummyMarker:
        def __init__(self, frame):
            self.frame = frame

    class DummyTrack:
        def __init__(self, frames):
            self.markers = [DummyMarker(f) for f in frames]

    track = DummyTrack(frames)
    length = get_track_length(track)
    print(f"Track length: {length}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tracksycle debug CLI")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    parser_cycle = subparsers.add_parser("cycle-models", help="Cycle motion models")
    parser_cycle.add_argument("steps", type=int, nargs="?", default=3)

    parser_length = subparsers.add_parser("track-length", help="Compute track length")
    parser_length.add_argument("frames", type=int, nargs="+")

    args = parser.parse_args(argv)
    configure_logger(debug=True)

    if args.cmd == "cycle-models":
        cycle_models(args.steps)
    elif args.cmd == "track-length":
        show_track_length(args.frames)


if __name__ == "__main__":
    main()

