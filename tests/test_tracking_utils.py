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
        try:
            super().remove(track)
        except ValueError:
            pass
    def get(self, name):
        for t in self:
            if t.name == name:
                return t
        return None


class DummyTrack:
    def __init__(self, name="T"):
        self.name = name
        self.markers = []
        self.select = False


class DummyMarker:
    def __init__(self, frame):
        self.frame = frame


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


class DummyLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)

    def debug(self, msg):
        pass


def test_safe_remove_track_operator(monkeypatch):
    called = {}
    clip = DummyClip()
    track = DummyTrack()
    clip.tracking.tracks.append(track)
    track.id_data = clip

    import bpy
    bpy.ops.clip.track_remove = lambda: called.setdefault("op", True)
    bpy.context = _setup_context(clip, with_area=True)

    logger = DummyLogger()
    result = tracking_utils.safe_remove_track(clip, track, logger=logger)
    assert called.get("op") is True
    assert track not in clip.tracking.tracks
    assert result is True
    assert logger.warnings == []


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
        try:
            list.remove(clip.tracking.tracks, t)
        except ValueError:
            pass
    clip.tracking.tracks.remove = dummy_remove

    logger = DummyLogger()
    result = tracking_utils.safe_remove_track(clip, track, logger=logger)
    assert called.get("op") is None
    assert called.get("removed") is True
    assert result is True
    assert logger.warnings  # warning should be emitted when no area found


def test_count_markers_in_frame():
    tracks = DummyTracks()
    t1 = DummyTrack("A")
    t1.markers = [DummyMarker(1), DummyMarker(3)]
    t2 = DummyTrack("B")
    t2.markers = [DummyMarker(2)]
    t3 = DummyTrack("C")
    tracks.extend([t1, t2, t3])

    assert tracking_utils.count_markers_in_frame(tracks, 1) == 1
    assert tracking_utils.count_markers_in_frame(tracks, 2) == 1
    assert tracking_utils.count_markers_in_frame(tracks, 3) == 1
    assert tracking_utils.count_markers_in_frame(tracks, 4) == 0
