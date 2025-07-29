import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from helpers.utils import strip_prefix, compute_detection_params, MIN_THRESHOLD


def test_strip_prefix():
    assert strip_prefix('GOOD_track001') == 'track001'
    assert strip_prefix('TRACK_test') == 'test'
    assert strip_prefix('NoPrefix') == 'NoPrefix'


def test_compute_detection_params_mid():
    th, margin, dist = compute_detection_params(0.5, 100, 200)
    assert th == 0.5
    assert margin == 96
    assert dist == 192


def test_compute_detection_params_min():
    th, margin, dist = compute_detection_params(0.0, 100, 200)
    assert th == MIN_THRESHOLD
    assert margin == 50
    assert dist == 100

