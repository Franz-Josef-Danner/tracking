import sys
import os
import time

# Ensure repo root is on sys.path so `Helper` package can be imported when pytest runs from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from Helper.metrics_provider_blender import BlenderMetricsProvider
from Helper.metrics_provider_backend import BackendMetricsProvider


def _validate_keys(d):
    keys = {"corr", "residual_px", "lost", "jump_px", "scale_delta", "rot_delta", "time_ms"}
    assert isinstance(d, dict)
    assert keys.issubset(set(d.keys()))


def test_blender_provider_fallback():
    p = BlenderMetricsProvider()
    out = p.fetch_tracking_metrics("0", 1)
    _validate_keys(out)
    # types
    assert isinstance(out["corr"], float)
    assert isinstance(out["lost"], bool)


def test_backend_provider_fallback():
    p = BackendMetricsProvider(url_template="http://invalid.local/metrics?roi_id={roi_id}&frame={frame}", timeout=0.01)
    out = p.fetch_tracking_metrics("0", 1)
    _validate_keys(out)
