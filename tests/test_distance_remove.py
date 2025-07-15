import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.detection import distance_remove


class DummyVector(list):
    def __sub__(self, other):
        return DummyVector([a - b for a, b in zip(self, other)])

    @property
    def length(self):
        return sum(c * c for c in self) ** 0.5

distance_remove.Vector = DummyVector

class DummyMarker:
    def __init__(self, co):
        self.co = co

class DummyTrack:
    def __init__(self, markers=None):
        self.markers = markers or []
    name = "DUMMY"

class DummyTracks(list):
    def find(self, name):
        for i, tr in enumerate(self):
            if tr.name == name:
                return i
        return -1

    def remove(self, track):
        self.remove_called_with = track
        try:
            idx = self.index(track)
        except ValueError:
            return
        del self[idx]
        self.removed = True

def test_distance_remove_empty_markers(monkeypatch):
    tracks = DummyTracks([DummyTrack(), DummyTrack([DummyMarker((0, 0))])])
    called = {}

    def dummy_safe_remove(clip, track):
        called['track'] = track
        tracks.remove(track)

    monkeypatch.setattr(distance_remove, 'safe_remove_track', dummy_safe_remove)

    distance_remove.distance_remove(tracks, (0, 0), 1.0)

    # The track with markers should be removed via safe_remove_track
    assert called.get('track') is not None
    assert getattr(tracks, 'removed', False)
    assert len(tracks) == 1

