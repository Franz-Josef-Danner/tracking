import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.operators.detect_features_operator import KAISERLICH_OT_detect_features


class DummyClip:
    size = (1000, 500)
    tracking = SimpleNamespace(tracks=[])


class DummyContext:
    def __init__(self, clip):
        self.scene = SimpleNamespace(debug_output=False)
        self.space_data = SimpleNamespace(clip=clip)


def test_operator_no_clip():
    op = KAISERLICH_OT_detect_features()
    op.report = lambda *a, **k: None
    context = DummyContext(None)
    result = op.execute(context)
    assert result == {'CANCELLED'}


def test_operator_calls_detection(monkeypatch):
    called = {}

    def dummy_detect(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
        called['args'] = (clip, threshold, margin, min_distance, logger)

    monkeypatch.setattr(
        'modules.operators.detect_features_operator.detect_features_no_proxy',
        dummy_detect,
    )

    op = KAISERLICH_OT_detect_features()
    op.report = lambda *a, **k: None
    op.threshold = 0.5
    op.margin = 10.0
    op.min_distance = 5
    context = DummyContext(DummyClip())

    result = op.execute(context)

    assert result == {'FINISHED'}
    clip, thr, marg, dist, _ = called['args']
    assert clip is context.space_data.clip
    assert thr == 0.5
    assert marg == 10.0
    assert dist == 5
