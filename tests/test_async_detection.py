import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.detection import async_detection


class DummyClip:
    def __init__(self):
        self.size = (1000, 1000)
        self.tracking = SimpleNamespace(
            settings=SimpleNamespace(default_pattern_size=11),
            tracks=[SimpleNamespace()],
        )


def test_async_detection_adjusts_threshold_and_limits_attempts(monkeypatch):
    thresholds = []
    marker_counts = [0, 0, 0, 0]

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        thresholds.append(threshold)
        count = marker_counts.pop(0)
        clip.tracking.tracks = [SimpleNamespace(name=f"Track{i}", markers=[SimpleNamespace(co=(0,0))]) for i in range(count)]
        return True

    monkeypatch.setattr(async_detection, "detect_features_no_proxy", dummy_detect)
    monkeypatch.setattr(async_detection, "safe_remove_track", lambda *a, **k: None)

    step_holder = {}

    def dummy_register(fn, first_interval=0.0):
        step_holder["fn"] = fn

    import bpy  # provided by conftest

    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=dummy_register))

    scene = SimpleNamespace(frame_current=1, min_marker_count=5)
    clip = DummyClip()

    async_detection.detect_features_async(scene, clip, attempts=3)
    step = step_holder["fn"]

    iterations = 1
    result = step()
    while result is not None:
        iterations += 1
        result = step()

    assert iterations == 4  # three retries and then stop
    assert len(set(thresholds)) > 1  # threshold adjusted over attempts
    assert thresholds[0] == 1.0
    assert iterations == len(thresholds)


def test_async_detection_stops_when_count_in_range(monkeypatch):
    thresholds = []
    marker_counts = [0, 17]

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        thresholds.append(threshold)
        count = marker_counts.pop(0)
        clip.tracking.tracks = [SimpleNamespace(name=f"Track{i}", markers=[SimpleNamespace(co=(0,0))]) for i in range(count)]
        return True

    monkeypatch.setattr(async_detection, "detect_features_no_proxy", dummy_detect)
    monkeypatch.setattr(async_detection, "safe_remove_track", lambda *a, **k: None)

    step_holder = {}

    def dummy_register(fn, first_interval=0.0):
        step_holder["fn"] = fn

    import bpy  # provided by conftest

    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=dummy_register))

    scene = SimpleNamespace(frame_current=1, min_marker_count=5)
    clip = DummyClip()

    async_detection.detect_features_async(scene, clip, attempts=5)
    step = step_holder["fn"]

    iterations = 1
    result = step()
    while result is not None:
        iterations += 1
        result = step()

    assert iterations == 2  # stop once marker count enters valid range
    assert thresholds[0] == 1.0
    assert iterations == len(thresholds)


def test_tracks_cleared_on_retry(monkeypatch):
    call_count = 0
    marker_counts = [15, 17]

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        count = marker_counts.pop(0)
        clip.tracking.tracks = [SimpleNamespace(name=f"Track{i}", markers=[SimpleNamespace(co=(0,0))]) for i in range(count)]
        return True

    def dummy_remove(clip, track, logger=None):
        nonlocal call_count
        call_count += 1

    monkeypatch.setattr(async_detection, "detect_features_no_proxy", dummy_detect)
    monkeypatch.setattr(async_detection, "safe_remove_track", dummy_remove)

    step_holder = {}

    def dummy_register(fn, first_interval=0.0):
        step_holder["fn"] = fn

    import bpy  # provided by conftest

    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=dummy_register))

    scene = SimpleNamespace(frame_current=1, min_marker_count=5)
    clip = DummyClip()

    async_detection.detect_features_async(scene, clip, attempts=5)
    step = step_holder["fn"]

    iterations = 1
    result = step()
    while result is not None:
        iterations += 1
        result = step()

    assert iterations == 2  # one retry
    assert call_count == 15
