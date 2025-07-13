import os
import sys
import types
import unittest
from unittest import mock

# Insert package root into sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Basic bpy stub
bpy = types.SimpleNamespace(
    ops=types.SimpleNamespace(clip=types.SimpleNamespace(track_markers=lambda **kwargs: None)),
    types=types.SimpleNamespace(Operator=object, Panel=object),
)
sys.modules['bpy'] = bpy

from tracking.auto_track_bidir import TRACK_OT_auto_track_bidir


class DummyTrack:
    def __init__(self, name):
        self.name = name
        self.select = False


class DummyClip:
    def __init__(self):
        track = DummyTrack("TRACK_test")
        self.tracking = types.SimpleNamespace(
            tracks=[track],
            objects=types.SimpleNamespace(active=types.SimpleNamespace(tracks=[track])),
        )


class DummyContext:
    def __init__(self, start, current):
        self.scene = types.SimpleNamespace(frame_start=start, frame_current=current)
        self.space_data = types.SimpleNamespace(type='CLIP_EDITOR', clip=DummyClip())


def execute_op(context):
    op = TRACK_OT_auto_track_bidir()
    return op.execute(context)


class AutoTrackBidirTests(unittest.TestCase):
    def test_skip_backward_at_start(self):
        context = DummyContext(start=1, current=1)
        with mock.patch.object(bpy.ops.clip, 'track_markers') as track:
            result = execute_op(context)
            self.assertEqual(track.call_count, 1)
            self.assertFalse(track.call_args[1]['backwards'])
            self.assertEqual(result, {'FINISHED'})

    def test_run_backward_when_not_start(self):
        context = DummyContext(start=1, current=2)
        with mock.patch.object(bpy.ops.clip, 'track_markers') as track:
            result = execute_op(context)
            self.assertEqual(track.call_count, 2)
            self.assertTrue(track.call_args_list[0][1]['backwards'])
            self.assertFalse(track.call_args_list[1][1]['backwards'])
            self.assertEqual(result, {'FINISHED'})


if __name__ == '__main__':
    unittest.main()
