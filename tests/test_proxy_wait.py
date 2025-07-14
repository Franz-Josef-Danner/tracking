import os
import threading
import time
import pytest

from types import SimpleNamespace

from modules.proxy.proxy_wait import (
    wait_for_stable_file,
    detect_features_in_ui_context,
    wait_for_proxy_and_trigger_detection,
    log_proxy_status,
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
            spaces=SimpleNamespace(active=SimpleNamespace(type="CLIP_EDITOR"), __iter__=lambda self: iter([self.active])),
        )
    ]
    class DummyOverride:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    dummy_context = SimpleNamespace(
        window=SimpleNamespace(screen=SimpleNamespace(areas=areas)),
        scene="scene",
        temp_override=lambda **kw: DummyOverride(**kw),
    )

    import bpy  # provided by conftest

    bpy.context = dummy_context
    bpy.ops.clip.detect_features = lambda *a, **k: called.update({"override": a[0] if a else None, **k})

    result = detect_features_in_ui_context(threshold=0.2, margin=5, min_distance=3, placement="FRAME")
    assert result is True
    assert called["threshold"] == 0.2
    assert called["margin"] == 5
    assert called["min_distance"] == 3
    assert called["placement"] == "FRAME"
    assert called["override"] is None


def test_wait_for_proxy_and_trigger_detection(tmp_path, monkeypatch):
    calls = {}

    areas = [
        SimpleNamespace(
            type="CLIP_EDITOR",
            regions=[SimpleNamespace(type="WINDOW")],
            spaces=SimpleNamespace(active=SimpleNamespace(type="CLIP_EDITOR"), __iter__=lambda self: iter([self.active])),
        )
    ]
    class DummyOverride:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    dummy_context = SimpleNamespace(
        window=SimpleNamespace(screen=SimpleNamespace(areas=areas)),
        scene="scene",
        temp_override=lambda **kw: DummyOverride(**kw),
    )

    import bpy  # provided by conftest

    bpy.context = dummy_context

    def dummy_register(fn, first_interval=0.0):
        calls["timer"] = True
        fn()

    bpy.app = SimpleNamespace(timers=SimpleNamespace(register=dummy_register))
    bpy.ops.clip.detect_features = lambda *a, **k: calls.update({"called": True})

    # run threads immediately
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    monkeypatch.setattr(threading.Thread, "__init__", lambda self, target: setattr(self, "run", target))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    proxy = tmp_path / "proxy.avi"
    proxy.write_bytes(b"data")

    wait_for_proxy_and_trigger_detection(None, str(proxy))
    assert calls.get("called")


def test_log_proxy_status(caplog):
    clip = SimpleNamespace(
        name="test",
        use_proxy=True,
        proxy=SimpleNamespace(build_25=False, build_50=True, build_75=False, build_100=False),
    )

    from modules.util.tracker_logger import configure_logger, TrackerLogger

    logger = configure_logger(debug=True)
    tlogger = TrackerLogger()
    with caplog.at_level(logger.level):
        log_proxy_status(clip, tlogger)
    assert "use_proxy=True" in caplog.text
    assert "build_50: True" in caplog.text
