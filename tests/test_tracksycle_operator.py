import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import modules.operators.tracksycle_operator as track_op
from modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle


class DummyWindowManager:
    def __init__(self):
        self.removed = None

    def event_timer_add(self, *a, **k):
        return "timer"

    def event_timer_remove(self, timer):
        self.removed = timer

    def modal_handler_add(self, op):
        pass


def test_modal_triggers_async_detection(monkeypatch, tmp_path):
    called = {}

    scene = SimpleNamespace(
        proxy_built=False,
        kaiserlich_feature_detection_done=False,
        kaiserlich_tracking_state="WAIT_FOR_PROXY",
    )

    wm = DummyWindowManager()
    context = SimpleNamespace(scene=scene, window_manager=wm)

    import bpy
    bpy.context = SimpleNamespace(scene=scene)
    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=lambda fn, first_interval=0.0: fn()))

    def dummy_async(scene_arg, clip_arg, logger=None, attempts=10):
        called["async"] = (scene_arg, clip_arg)
        scene_arg.kaiserlich_feature_detection_done = True

    monkeypatch.setattr(track_op, "detect_features_async", dummy_async)

    proxy_path = tmp_path / "proxy.avi"
    proxy_path.write_text("data")

    op = KAISERLICH_OT_auto_track_cycle()
    op._timer = "timer"
    op._proxy_paths = [str(proxy_path)]
    op._clip = SimpleNamespace(use_proxy=True)
    op._logger = SimpleNamespace(info=lambda *a, **k: None)

    result = op.modal(context, SimpleNamespace(type="TIMER"))

    assert result == {"RUNNING_MODAL"}
    assert called.get("async")
    assert scene.proxy_built is True
    assert scene.kaiserlich_tracking_state == "DETECTING"
    assert wm.removed == "timer"
    assert op._clip.use_proxy is False
