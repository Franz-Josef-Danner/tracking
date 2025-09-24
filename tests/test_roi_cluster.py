import types
import sys
import math
from pathlib import Path
import importlib


class DummyMarker:
    def __init__(self, frame, co):
        self.frame = frame
        self.co = co


class DummyTrack:
    def __init__(self, name, markers, select=False, roi_id=None, error=0.1):
        self.name = name
        self.markers = markers
        self.select = select
        self.roi_id = roi_id
        self.error = error


class DummyTracking:
    def __init__(self, tracks):
        self.tracks = tracks


class DummyClip:
    def __init__(self, size, tracking):
        self.size = size
        self.tracking = tracking


def make_clip_with_tracks():
    # create tracks in two spatial clusters
    t1 = DummyTrack("t1", [DummyMarker(1, (0.1, 0.1)), DummyMarker(2, (0.11, 0.11))], select=True, roi_id=0)
    t2 = DummyTrack("t2", [DummyMarker(1, (0.12, 0.1)), DummyMarker(2, (0.13, 0.11))], select=True, roi_id=0)
    t3 = DummyTrack("t3", [DummyMarker(1, (0.8, 0.8)), DummyMarker(2, (0.81, 0.79))], select=True, roi_id=0)
    t4 = DummyTrack("t4", [DummyMarker(1, (0.81, 0.82)), DummyMarker(2, (0.82, 0.83))], select=True, roi_id=0)

    tracks = [t1, t2, t3, t4]
    tracking = DummyTracking(tracks)
    clip = DummyClip((1000, 1000), tracking)
    return clip


def test_cluster_tracks_basic(monkeypatch):
    # ensure project root is importable
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    clip = make_clip_with_tracks()
    fake_bpy = types.ModuleType("bpy")
    fake_bpy.context = types.SimpleNamespace(edit_movieclip=clip)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    roi = importlib.import_module("Helper.roi")

    clusters = roi.cluster_tracks(roi_id=0)
    # Expect at least 2 clusters (two groups of two tracks)
    assert isinstance(clusters, list)
    assert len(clusters) >= 2
    all_inliers = [i for c in clusters for i in c.get("inliers", [])]
    # ensure all track names present
    for name in ["t1", "t2", "t3", "t4"]:
        assert name in all_inliers


if __name__ == "__main__":
    test_cluster_tracks_basic()
    print("ok")
