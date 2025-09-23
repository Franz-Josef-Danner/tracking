# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/init_params.py – Startparameter pro ROI

- pattern p0: round_odd(diag/150) clamp 9..41
- alpha (search/pattern): default 3; up/down je nach Motion/Divergenz
- Channel-Default: Y; Channel-Selektion als separater Schritt
"""
from __future__ import annotations

from typing import Tuple
import math

from .governance import LIMITS
from .strm import ROI

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

__all__ = ("init_pattern_search", "select_channel")


def _clip_size(context) -> Tuple[int, int]:
    clip = getattr(context, "edit_movieclip", None)
    if not clip and bpy is not None:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            pass
    if not clip:
        return (0, 0)
    try:
        return int(clip.size[0]), int(clip.size[1])
    except Exception:
        return (0, 0)


def _round_odd(x: float) -> int:
    v = int(round(x))
    return v if v % 2 == 1 else v + 1


def _round_even(x: float) -> int:
    v = int(round(x))
    return v if v % 2 == 0 else v + 1


def init_pattern_search(context, roi: ROI) -> ROI:
    W, H = _clip_size(context)
    diag = math.sqrt(max(1, W) ** 2 + max(1, H) ** 2)
    p0 = _round_odd(diag / 150.0)
    p0 = LIMITS.clamp_pattern(max(9, min(41, p0)))

    # alpha: default 3; Bewegung/Divergenz heuristisch
    a = 3
    if roi.v_motion > 0.6 or roi.phi_div > 0.25:
        a = min(4, a + 1)
    if roi.tau_tex < 0.3:
        a = max(2, a - 1)

    roi.pattern = int(p0)
    roi.alpha = int(a)
    return roi


def select_channel(context, roi: ROI) -> ROI:
    """Einfacher Pre-Pass: bevorzugt Y (Luma). Optionale Erweiterung: G bei schwacher Textur.
    Setzt Tracking-Defaults im Clip (global) entsprechend.
    """
    # Heuristik: niedrige Textur → G-Kanal probieren, sonst Y
    roi.channel = "G" if roi.tau_tex < 0.35 else "Y"

    if bpy is None:
        return roi

    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            clip = None
    if not clip:
        return roi

    ts = clip.tracking.settings
    # Y/G Mapping auf RGB-Schalter (Blender hat keinen direkten Luma-Mode hier)
    if roi.channel == "Y":
        ts.use_default_red_channel = True
        ts.use_default_green_channel = True
        ts.use_default_blue_channel = True
    else:  # "G"
        ts.use_default_red_channel = False
        ts.use_default_green_channel = True
        ts.use_default_blue_channel = False
    return roi
