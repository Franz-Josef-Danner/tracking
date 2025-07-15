import os, sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.util import tracking_utils


class DummyOverride:
    def __init__(self, **kw):
        self.kw = kw
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class DummyTracks(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.active = None
        self.removed = None
    def remove(self, track):
        self.removed = track
    def get(self, name):
        for t in self:
            if t.name == name:
                return t
        return None


class DummyTrack:
    def __init__(self, name="T"):
        self.name = name
        self.markers = []


class DummyClip:
    def __init__(self):
        self.tracking = SimpleNamespace(tracks=DummyTracks())


def _setup_context(clip, with_area=True):
    if with_area:
        areas = [SimpleNamespace(type="CLIP_EDITOR", regions=[SimpleNamespace(type="WINDOW")], spaces=SimpleNamespace(active=SimpleNamespace(type="CLIP_EDITOR")))]
    else:
        areas = []
    return SimpleNamespace(
        screen=SimpleNamespace(areas=areas),
        temp_override=lambda **kw: DummyOverride(**kw),
    )


def test_safe_remove_track_operator(monkeypatch):
    called = {}
    clip = DummyClip()
    track = DummyTrack()
    clip.tracking.tracks.append(track)
    track.id_data = clip

    import bpy
    bpy.ops.clip.track_remove = lambda: called.setdefault("op", True)
    bpy.context = _setup_context(clip, with_area=True)

    tracking_utils.safe_remove_track(clip, track)
    assert called.get("op") is True
    assert clip.tracking.tracks.removed is None


def test_safe_remove_track_fallback(monkeypatch):
    called = {}
    clip = DummyClip()
    track = DummyTrack()
    clip.tracking.tracks.append(track)
    track.id_data = clip

    import bpy
    bpy.ops.clip.track_remove = lambda: called.setdefault("op", True)
    bpy.context = _setup_context(clip, with_area=False)

    def dummy_remove(t):
        called["removed"] = True
    clip.tracking.tracks.remove = dummy_remove

    tracking_utils.safe_remove_track(clip, track)
    assert called.get("op") is None
    assert called.get("removed") is True
