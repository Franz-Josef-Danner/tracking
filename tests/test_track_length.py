import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.tracking.track_length import get_track_length


class DummyMarker:
    def __init__(self, frame):
        self.frame = frame


class DummyTrack:
    def __init__(self, frames):
        self.markers = [DummyMarker(f) for f in frames]


def test_get_track_length():
    track = DummyTrack([1, 5, 10])
    assert get_track_length(track) == 9


def test_get_track_length_empty():
    track = DummyTrack([])
    assert get_track_length(track) == 0

