import os
import sys
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


def test_track_exists_bpy_collection():
    class DummyBpyTracks:
        def __init__(self, tracks):
            self._tracks = {t.name: t for t in tracks}

        def __contains__(self, name):  # expects a track name
            return name in self._tracks

        def get(self, name):
            return self._tracks.get(name)

        def __iter__(self):
            return iter(self._tracks.values())

    t1 = DummyTrack("A")
    tracks = DummyBpyTracks([t1])

    assert tracking_utils._track_exists(tracks, t1)
    assert not tracking_utils._track_exists(tracks, DummyTrack("B"))


def test_hard_remove_new_tracks(monkeypatch):
    clip = DummyClip()
    clip.tracking.tracks.extend([
        DummyTrack("NEW_001"),
        DummyTrack("KEEP"),
        DummyTrack("NEW_002"),
    ])

    def dummy_safe_remove(_clip, track, logger=None):
        clip.tracking.tracks.remove(track)
        return True

    monkeypatch.setattr(tracking_utils, "safe_remove_track", dummy_safe_remove)

    tracking_utils.hard_remove_new_tracks(clip)

    names = [t.name for t in clip.tracking.tracks]
    assert names == ["KEEP"]


def test_hard_remove_new_tracks_empty(monkeypatch):
    clip = DummyClip()
    t1 = DummyTrack("NEW_001")
    t1.markers = []
    t2 = DummyTrack("NEW_002")
    t2.markers = []
    clip.tracking.tracks.extend([t1, t2])

    def dummy_safe_remove(_clip, track, logger=None):
        # simulate failure: do not remove t1
        return track is not t1

    monkeypatch.setattr(tracking_utils, "safe_remove_track", dummy_safe_remove)

    tracking_utils.hard_remove_new_tracks(clip)

    assert clip.tracking.tracks == []


def test_rename_new_to_track(monkeypatch):
    clip = DummyClip()
    clip.tracking.tracks.extend([
        DummyTrack("NEW_001"),
        DummyTrack("NEW_002"),
    ])

    tracking_utils.rename_new_to_track(clip)

    names = [t.name for t in clip.tracking.tracks]
    assert names == ["TRACK_000", "TRACK_001"]
