import math
import sys
import types
import unittest
from unittest import mock

# Patch bpy before importing modules that expect it
sys.modules.setdefault('bpy', types.SimpleNamespace())
sys.modules.setdefault('mathutils', types.SimpleNamespace(Vector=lambda co=None: types.SimpleNamespace(co=co)))

from tracking import adjust_marker_count_plus as acp
from tracking import rename_new
from tracking import margin_utils
from tracking import utils
from tracking import delete_helpers


class DummyScene:
    def __init__(self, count):
        self.min_marker_count_plus = count


class DummyTrack:
    def __init__(self, name):
        self.name = name


class DummyClip(dict):
    def __init__(self, width):
        super().__init__()
        self.size = (width, width)


class AdjustMarkerCountPlusTests(unittest.TestCase):
    def test_no_change_when_new_count_high(self):
        scene = DummyScene(10)
        result = acp.adjust_marker_count_plus(scene, 12)
        self.assertEqual(result, 10)
        self.assertEqual(scene.min_marker_count_plus, 10)

    def test_reduce_expected_count(self):
        scene = DummyScene(10)
        result = acp.adjust_marker_count_plus(scene, 8)
        self.assertEqual(result, 9)
        self.assertEqual(scene.min_marker_count_plus, 9)

    def test_never_below_one(self):
        scene = DummyScene(1)
        result = acp.adjust_marker_count_plus(scene, 0)
        self.assertEqual(result, 1)
        self.assertEqual(scene.min_marker_count_plus, 1)

    def test_increase_marker_count_plus(self):
        scene = DummyScene(10)
        result = acp.increase_marker_count_plus(scene)
        self.assertEqual(result, 11)
        self.assertEqual(scene.min_marker_count_plus, 11)

    def test_decrease_marker_count_plus(self):
        scene = DummyScene(10)
        result = acp.decrease_marker_count_plus(scene, base_value=8)
        self.assertEqual(result, 9)
        self.assertEqual(scene.min_marker_count_plus, 9)


class RenameTracksTests(unittest.TestCase):
    def test_add_prefix(self):
        track = DummyTrack("foo")
        rename_new.rename_tracks([track])
        self.assertEqual(track.name, "NEW_foo")

    def test_strip_existing_prefix(self):
        track = DummyTrack("TRACK_bar")
        rename_new.rename_tracks([track])
        self.assertEqual(track.name, "NEW_bar")

    def test_custom_prefix(self):
        track = DummyTrack("GOOD_baz")
        rename_new.rename_tracks([track], prefix="TRACK_")
        self.assertEqual(track.name, "TRACK_baz")


class EnsureMarginDistanceTests(unittest.TestCase):
    def test_initializes_properties(self):
        clip = DummyClip(200)
        margin, distance, base = margin_utils.ensure_margin_distance(clip)
        self.assertEqual(margin, 1)
        self.assertEqual(distance, 10)
        self.assertEqual(base, 10)
        self.assertEqual(clip["MARGIN"], 1)
        self.assertEqual(clip["DISTANCE"], 10)

    def test_scaling(self):
        clip = DummyClip(200)
        margin_utils.ensure_margin_distance(clip)
        margin, distance, base = margin_utils.ensure_margin_distance(clip, threshold=0.1)
        scale = math.log10(0.1 * 100000) / 5
        expected_margin = max(1, int(clip["MARGIN"] * scale))
        expected_distance = max(1, int(clip["DISTANCE"] * scale))
        self.assertEqual(margin, expected_margin)
        self.assertEqual(distance, expected_distance)
        self.assertEqual(base, clip["DISTANCE"])


class GetActiveClipTests(unittest.TestCase):
    class DummyContext:
        def __init__(self, space_clip=None, scene_clip=None):
            self.space_data = types.SimpleNamespace(clip=space_clip) if space_clip else None
            self.scene = types.SimpleNamespace(clip=scene_clip)

    def test_returns_space_clip_when_available(self):
        clip = object()
        ctx = self.DummyContext(space_clip=clip, scene_clip=object())
        self.assertIs(utils.get_active_clip(ctx), clip)

    def test_falls_back_to_scene(self):
        clip = object()
        ctx = self.DummyContext(space_clip=None, scene_clip=clip)
        self.assertIs(utils.get_active_clip(ctx), clip)


class DeleteNewMarkersTests(unittest.TestCase):
    def test_returns_zero_without_clip(self):
        ctx = types.SimpleNamespace(space_data=None, screen=types.SimpleNamespace(areas=[]))
        removed = delete_helpers.delete_new_markers(ctx)
        self.assertEqual(removed, 0)


if __name__ == "__main__":
    unittest.main()
