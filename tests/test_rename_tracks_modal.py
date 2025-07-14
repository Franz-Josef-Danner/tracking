import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import modules.operators.rename_tracks_modal as rename_modal
from modules.operators.rename_tracks_modal import KAISERLICH_OT_rename_tracks_modal

class DummyWindowManager:
    def __init__(self):
        self.added = None
        self.removed = None
        self.handlers = []

    def event_timer_add(self, time, window=None):
        self.added = (time, window)
        return SimpleNamespace()

    def event_timer_remove(self, timer):
        self.removed = timer

    def modal_handler_add(self, op):
        self.handlers.append(op)


class DummyContext:
    def __init__(self, clip):
        self.scene = SimpleNamespace()
        self.space_data = SimpleNamespace(clip=clip)
        self.window_manager = DummyWindowManager()
        self.window = SimpleNamespace()


class DummyTrack:
    def __init__(self, name):
        self.name = name


class DummyEvent:
    def __init__(self, type):
        self.type = type


def test_execute_without_clip():
    op = KAISERLICH_OT_rename_tracks_modal()
    op.report = lambda *a, **k: None
    context = DummyContext(None)
    result = op.execute(context)
    assert result == {'CANCELLED'}


def test_modal_renames_tracks(monkeypatch):
    monkeypatch.setattr(rename_modal, 'VALID_EVENT_TYPES', {'TIMER'})

    op = KAISERLICH_OT_rename_tracks_modal()
    op.report = lambda *a, **k: None
    tracks = [DummyTrack('foo'), DummyTrack('TRACK_bar')]
    clip = SimpleNamespace(tracking=SimpleNamespace(tracks=tracks))
    context = DummyContext(clip)

    timer_result = op.execute(context)
    assert timer_result == {'RUNNING_MODAL'}

    # event not in VALID_EVENT_TYPES
    result = op.modal(context, DummyEvent('MOUSEMOVE'))
    assert result == {'PASS_THROUGH'}

    # first timer event -> rename first track
    result = op.modal(context, DummyEvent('TIMER'))
    assert result == {'PASS_THROUGH'}
    assert tracks[0].name == 'TRACK_foo'
    assert context.window_manager.removed is None

    # second timer event -> rename second track already correctly named
    result = op.modal(context, DummyEvent('TIMER'))
    assert result == {'PASS_THROUGH'}
    assert tracks[1].name == 'TRACK_bar'
    assert context.window_manager.removed is None

    # final timer event -> finished
    result = op.modal(context, DummyEvent('TIMER'))
    assert result == {'FINISHED'}
    assert context.window_manager.removed is not None
