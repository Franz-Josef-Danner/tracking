import math
import sys
import types
import unittest
from unittest import mock

# Patch Blender modules before importing addon code
dummy_bpy = types.SimpleNamespace(
    types=types.SimpleNamespace(Operator=object, Panel=object, AddonPreferences=object),
    ops=types.SimpleNamespace(),
    props=types.SimpleNamespace(),
)
sys.modules.setdefault('bpy', dummy_bpy)
sys.modules.setdefault('mathutils', types.SimpleNamespace())
bpy = sys.modules['bpy']

import adjust_marker_count_plus as acp
import rename_new
import margin_utils
import marker_count_plus as mcp


class DummyScene:
    def __init__(self, count):
        self.min_marker_count_plus = count
        self.marker_count_plus_min = 0
        self.marker_count_plus_max = 0
        self.new_marker_count = 0


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


class RefreshMarkerCountPlusTests(unittest.TestCase):
    def test_updates_ranges(self):
        scene = DummyScene(10)
        mcp.refresh_marker_count_plus(scene)
        self.assertEqual(scene.marker_count_plus_min, 8)
        self.assertEqual(scene.marker_count_plus_max, 12)
        self.assertEqual(scene.new_marker_count, 10)


class ProxyFlagTests(unittest.TestCase):
    def test_detection_disables_proxy(self):
        import detect

        class Clip:
            def __init__(self):
                self.use_proxy = True
                self.tracking = types.SimpleNamespace(
                    tracks=[],
                    settings=types.SimpleNamespace(
                        default_pattern_size=0,
                        default_search_size=0,
                        default_motion_model="",
                    ),
                )

        clip = Clip()
        scene = types.SimpleNamespace(
            min_marker_count_plus=1,
            min_marker_count=1,
            new_marker_count=0,
        )
        context = types.SimpleNamespace(
            scene=scene,
            space_data=types.SimpleNamespace(clip=clip),
        )

        bpy.ops = types.SimpleNamespace(
            clip=types.SimpleNamespace(
                detect_features=lambda **kw: clip.tracking.tracks.append(
                    DummyTrack("x")
                ),
                delete_track=lambda: clip.tracking.tracks.clear(),
            )
        )

        with mock.patch.object(detect, "compute_margin_distance"), \
                mock.patch.object(detect, "ensure_margin_distance", return_value=(1, 1, 1)), \
                mock.patch.object(detect, "adjust_marker_count_plus"):
            op = detect.DetectFeaturesCustomOperator()
            op.report = lambda *a, **k: None
            op.execute(context)

        self.assertFalse(clip.use_proxy)

    def test_iterative_detect_disables_proxy(self):
        import iterative_detect

        class Clip:
            def __init__(self):
                self.use_proxy = True
                self.tracking = types.SimpleNamespace(
                    tracks=[],
                    settings=types.SimpleNamespace(
                        default_pattern_size=0,
                        default_motion_model="",
                    ),
                )

        clip = Clip()
        scene = types.SimpleNamespace(
            marker_count_plus_min=0,
            marker_count_plus_max=2,
            min_marker_count_plus=1,
            new_marker_count=0,
        )
        context = types.SimpleNamespace(
            scene=scene,
            space_data=types.SimpleNamespace(clip=clip),
        )

        bpy.ops = types.SimpleNamespace(
            clip=types.SimpleNamespace(
                detect_features=lambda **kw: clip.tracking.tracks.append(
                    DummyTrack("x")
                ),
                delete_track=lambda: clip.tracking.tracks.clear(),
            )
        )

        with mock.patch.object(iterative_detect, "compute_margin_distance"), \
                mock.patch.object(iterative_detect, "ensure_margin_distance", return_value=(1, 1, 1)), \
                mock.patch.object(iterative_detect, "rename_new_tracks"), \
                mock.patch.object(iterative_detect, "count_new_markers", return_value=1):
            iterative_detect.detect_until_count_matches(context)

        self.assertFalse(clip.use_proxy)

    def test_iterative_detect_uses_error_threshold(self):
        import iterative_detect

        class Clip:
            def __init__(self):
                self.use_proxy = True
                self.tracking = types.SimpleNamespace(
                    tracks=[],
                    settings=types.SimpleNamespace(
                        default_pattern_size=0,
                        default_motion_model="",
                    ),
                )

        clip = Clip()
        scene = types.SimpleNamespace(
            marker_count_plus_min=0,
            marker_count_plus_max=2,
            min_marker_count_plus=1,
            new_marker_count=0,
            error_threshold=0.5,
        )
        context = types.SimpleNamespace(
            scene=scene,
            space_data=types.SimpleNamespace(clip=clip),
        )

        bpy.ops = types.SimpleNamespace(
            clip=types.SimpleNamespace(
                detect_features=lambda **kw: clip.tracking.tracks.append(
                    DummyTrack("x")
                ),
                delete_track=lambda: clip.tracking.tracks.clear(),
            )
        )

        with mock.patch.object(iterative_detect, "compute_margin_distance"), \
                mock.patch.object(iterative_detect, "ensure_margin_distance", return_value=(1, 1, 1)) as emd, \
                mock.patch.object(iterative_detect, "rename_new_tracks"), \
                mock.patch.object(iterative_detect, "count_new_markers", return_value=1):
            iterative_detect.detect_until_count_matches(context)

        emd.assert_any_call(clip, 0.5)

    def test_track_cycle_enables_proxy(self):
        import track_cycle

        class Clip:
            def __init__(self):
                self.use_proxy = False
                self.tracking = types.SimpleNamespace(tracks=[])

        clip = Clip()
        context = types.SimpleNamespace(
            space_data=types.SimpleNamespace(clip=clip),
            scene=types.SimpleNamespace(frame_current=1),
        )

        bpy.ops = types.SimpleNamespace(
            clip=types.SimpleNamespace(track_markers=lambda **kw: None)
        )

        track_cycle.auto_track_bidirectional(context)
        self.assertTrue(clip.use_proxy)


if __name__ == "__main__":
    unittest.main()
