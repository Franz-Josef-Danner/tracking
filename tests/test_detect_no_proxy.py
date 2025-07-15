import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.detection.detect_no_proxy import detect_features_no_proxy


class DummyClip:
    def __init__(self):
        self.name = "clip"
        self.size = (1000, 500)
        self.proxy = SimpleNamespace(build_50=True)
        self.use_proxy = True
        self.tracking = SimpleNamespace(tracks=[])


def _setup_context(areas, called):
    class DummyOverride:
        def __init__(self, **kw):
            called["override"] = kw

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    return SimpleNamespace(
        screen=SimpleNamespace(areas=areas),
        scene="scene",
        temp_override=lambda **kw: DummyOverride(**kw),
    )


def test_detect_features_no_proxy_ui_context(monkeypatch):
    called = {}
    areas = [SimpleNamespace(type="CLIP_EDITOR", regions=[SimpleNamespace(type="WINDOW")])]
    import bpy
    bpy.context = _setup_context(areas, called)

    def dummy_detect(*a, **kw):
        called.update(kw)
        called["args"] = a
        return {"FINISHED"}

    monkeypatch.setattr(bpy.ops.clip, "detect_features", dummy_detect)
    monkeypatch.setattr(
        "modules.detection.detect_no_proxy.log_proxy_status", lambda *a, **k: None
    )

    clip = DummyClip()
    result = detect_features_no_proxy(clip, threshold=0.5, margin=10, min_distance=5)
    assert result is True
    assert called["threshold"] == 0.5
    assert called["margin"] == 10
    assert called["min_distance"] == 5
    assert called["args"] == ()
    assert called["override"]["clip"] is clip
    assert called["override"]["area"] is areas[0]
    assert called["override"]["region"] is areas[0].regions[0]
    assert called["override"]["scene"] == "scene"


def test_detect_features_no_proxy_no_clip_editor(monkeypatch):
    called = {}
    import bpy
    bpy.context = _setup_context([], called)

    monkeypatch.setattr(bpy.ops.clip, "detect_features", lambda *a, **k: None)
    monkeypatch.setattr(
        "modules.detection.detect_no_proxy.log_proxy_status", lambda *a, **k: None
    )

    clip = DummyClip()
    assert detect_features_no_proxy(clip) is False
