import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import modules.operators.tracking_marker_operator as marker_op


class DummyClip:
    def __init__(self):
        self.size = (1000, 1000)
        self.tracking = SimpleNamespace(tracks=[])


class DummyContext:
    def __init__(self, clip):
        self.scene = SimpleNamespace(frame_current=1, min_marker_count=5, debug_output=False)
        self.space_data = SimpleNamespace(clip=clip,
                                         detection_margin=0,
                                         detection_distance=0,
                                         detection_threshold=0)


def test_operator_no_clip():
    op = marker_op.KAISERLICH_OT_tracking_marker()
    op.report = lambda *a, **k: None
    context = DummyContext(None)
    result = op.execute(context)
    assert result == {'CANCELLED'}


def test_operator_adjusts_threshold(monkeypatch):
    thresholds = []
    marker_counts = [0, 0, 0]

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        thresholds.append(threshold)
        count = marker_counts.pop(0)
        clip.tracking.tracks = [SimpleNamespace(name=f"Track{i}", markers=[SimpleNamespace(co=(0,0))]) for i in range(count)]
        return True

    monkeypatch.setattr(marker_op, "detect_features_no_proxy", dummy_detect)
    monkeypatch.setattr(marker_op, "distance_remove", lambda *a, **k: None)
    monkeypatch.setattr(marker_op, "hard_remove_new_tracks", lambda *a, **k: [])

    clip = DummyClip()
    context = DummyContext(clip)

    op = marker_op.KAISERLICH_OT_tracking_marker()
    op.report = lambda *a, **k: None
    op.attempts = 3

    op.execute(context)

    assert len(set(thresholds)) > 1
    assert thresholds[0] == 1.0
    assert len(thresholds) == 3


def test_distance_filter_uses_current_frame(monkeypatch):
    captured = {}

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        good = SimpleNamespace(
            name="GOOD_1",
            markers=[SimpleNamespace(frame=1, co=(1,1)), SimpleNamespace(frame=2, co=(2,2))],
        )
        clip.tracking.tracks = [good, SimpleNamespace(name="Track0", markers=[SimpleNamespace(co=(0,0))])]
        return True

    def dummy_distance(tracks, pos, margin, logger=None):
        captured['pos'] = pos

    monkeypatch.setattr(marker_op, "detect_features_no_proxy", dummy_detect)
    monkeypatch.setattr(marker_op, "distance_remove", dummy_distance)
    monkeypatch.setattr(marker_op, "hard_remove_new_tracks", lambda *a, **k: [])

    clip = DummyClip()
    context = DummyContext(clip)
    context.scene.frame_current = 2

    op = marker_op.KAISERLICH_OT_tracking_marker()
    op.report = lambda *a, **k: None
    op.attempts = 1

    op.execute(context)

    assert captured.get('pos') == (2,2)
