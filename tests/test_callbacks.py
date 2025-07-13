import os
import sys
import types
import unittest

# Ensure the tracking package can be imported when tests are run from the
# repository root. Insert the parent directory (which contains the package) at the start of ``sys.path``.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Patch bpy before importing modules that expect it
sys.modules.setdefault('bpy', types.SimpleNamespace())

import tracking
from tracking import register_after_detect_callback, unregister_after_detect_callback


def dummy_cb(context):
    pass


class AfterDetectCallbackTests(unittest.TestCase):
    def tearDown(self):
        unregister_after_detect_callback()

    def test_register_sets_callback(self):
        register_after_detect_callback(dummy_cb)
        self.assertIs(tracking.after_detect_callback, dummy_cb)

    def test_unregister_clears_callback(self):
        register_after_detect_callback(dummy_cb)
        unregister_after_detect_callback()
        self.assertIsNone(tracking.after_detect_callback)


if __name__ == "__main__":
    unittest.main()
