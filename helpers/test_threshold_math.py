from .threshold_math import compute_threshold_factor, adjust_threshold
from .utils import MIN_THRESHOLD


def test_compute_threshold_factor():
    factor = compute_threshold_factor(0.5)
    assert 0.0 < factor <= 1.0


def test_adjust_threshold_clamp():
    val = adjust_threshold(0.5, 10, 20)
    assert MIN_THRESHOLD <= val <= 1.0

