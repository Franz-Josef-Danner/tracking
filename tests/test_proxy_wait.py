import os
import threading
import time
import pytest

from types import SimpleNamespace

from modules.proxy.proxy_wait import (
    wait_for_stable_file,
    detect_features_in_ui_context,
    wait_for_proxy_and_trigger_detection,
)


def test_wait_for_stable_file(tmp_path):
    path = tmp_path / "file.txt"

    def writer():
        with open(path, "wb") as fh:
            fh.write(b"a")
        time.sleep(0.2)
        with open(path, "ab") as fh:
            fh.write(b"b")

    t = threading.Thread(target=writer)
    t.start()

    assert wait_for_stable_file(path, timeout=2, check_interval=0.1, stable_time=3)
    t.join()


def test_wait_for_stable_file_timeout(tmp_path):
    path = tmp_path / "missing.txt"
    with pytest.raises(TimeoutError):
        wait_for_stable_file(path, timeout=0.3, check_interval=0.1, stable_time=2)


def test_detect_features_in_ui_context(monkeypatch):
    called = {}

    areas = [
        SimpleNamespace(
            type="CLIP_EDITOR",
            regions=[SimpleNamespace(type="WINDOW")],
            spaces=SimpleNamespace(active="active"),
        )
    ]
    dummy_context = SimpleNamespace(
        window=SimpleNamespace(screen=SimpleNamespace(areas=areas)),
        scene="scene",
    )

    import bpy  # provided by conftest

    bpy.context = dummy_context
    bpy.ops.clip.detect_features = lambda override=None, **k: called.update({"override": override, **k})

    result = detect_features_in_ui_context(threshold=0.2, margin=5, min_distance=3, placement="FRAME")
    assert result is True
    assert called["threshold"] == 0.2
    assert called["margin"] == 5
    assert called["min_distance"] == 3
    assert called["placement"] == "FRAME"
    assert called["override"]["area"] is areas[0]


def test_wait_for_proxy_and_trigger_detection(tmp_path, monkeypatch):
    calls = {}

    areas = [
        SimpleNamespace(
            type="CLIP_EDITOR",
            regions=[SimpleNamespace(type="WINDOW")],
            spaces=SimpleNamespace(active="active"),
        )
    ]
    dummy_context = SimpleNamespace(
        window=SimpleNamespace(screen=SimpleNamespace(areas=areas)),
        scene="scene",
    )

    import bpy  # provided by conftest

    bpy.context = dummy_context

    def dummy_register(fn, first_interval=0.0):
        calls["timer"] = True
        fn()

    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=dummy_register))
    bpy.ops.clip.detect_features = lambda override=None, **k: calls.update({"called": True})

    # run threads immediately
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    monkeypatch.setattr(threading.Thread, "__init__", lambda self, target: setattr(self, "run", target))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    proxy = tmp_path / "proxy.avi"
    proxy.write_bytes(b"data")

    wait_for_proxy_and_trigger_detection(None, str(proxy))
    assert calls.get("called")
