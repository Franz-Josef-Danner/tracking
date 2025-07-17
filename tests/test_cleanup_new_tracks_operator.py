from types import SimpleNamespace
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.operators.cleanup_new_tracks_operator import KAISERLICH_OT_cleanup_new_tracks

class DummyClip:
    def __init__(self):
        self.tracking = SimpleNamespace(tracks=[])

class DummyContext:
    def __init__(self, clip):
        self.scene = SimpleNamespace(debug_output=False)
        self.space_data = SimpleNamespace(clip=clip)


def test_operator_no_clip():
    op = KAISERLICH_OT_cleanup_new_tracks()
    op.report = lambda *a, **k: None
    context = DummyContext(None)
    result = op.execute(context)
    assert result == {'CANCELLED'}


def test_operator_calls_hard_remove(monkeypatch):
    called = {}
    op = KAISERLICH_OT_cleanup_new_tracks()
    op.report = lambda *a, **k: called.setdefault('report', True)
    context = DummyContext(DummyClip())

    def dummy_remove(clip, logger=None):
        called['clip'] = clip
        return []

    monkeypatch.setattr(
        'modules.operators.cleanup_new_tracks_operator.hard_remove_new_tracks',
        dummy_remove,
    )

    result = op.execute(context)

    assert result == {'FINISHED'}
    assert called.get('clip') is context.space_data.clip
