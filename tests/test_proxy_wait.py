import os
import threading
import time
import pytest

from modules.proxy.proxy_wait import wait_for_stable_file


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
