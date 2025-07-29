import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from helpers.marker_helpers import has_active_marker, select_tracks_by_prefix

class Vec:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    @property
    def length_squared(self):
        return self.x * self.x + self.y * self.y

class DummyMarker:
    def __init__(self, frame, mute=False, co=None):
        self.frame = frame
        self.mute = mute
        self.co = co or Vec(1, 1)

class Markers:
    def __init__(self, markers):
        self._dict = {m.frame: m for m in markers}
    def find_frame(self, frame, exact=False):
        return self._dict.get(frame)

class DummyTrack:
    def __init__(self, name, markers):
        self.name = name
        self.markers = Markers(markers)
        self.select = False

class DummyClip:
    def __init__(self, tracks):
        self.tracking = SimpleNamespace(tracks=tracks)

from types import SimpleNamespace

def test_has_active_marker():
    track = DummyTrack('T1', [DummyMarker(1)])
    assert has_active_marker([track], 1)
    track2 = DummyTrack('T2', [DummyMarker(1, mute=True)])
    assert not has_active_marker([track2], 1)
    track3 = DummyTrack('T3', [DummyMarker(1, co=Vec(0, 0))])
    assert not has_active_marker([track3], 1)


def test_select_tracks_by_prefix():
    t1 = DummyTrack('GOOD_a', [])
    t2 = DummyTrack('BAD_b', [])
    clip = DummyClip([t1, t2])
    select_tracks_by_prefix(clip, 'GOOD_')
    assert t1.select is True
    assert t2.select is False


