"""Helper-Bootstrap für Parameterberechnung.

Berechnet Parameter aus Clip-Auflösung und Eingabewert ef.
"""
from __future__ import annotations

import math
import importlib
import bpy
from . import marker_size as helper_marker_size


def compute_parameters(context: bpy.types.Context, ef: int):
    clip = _get_active_clip(context)
    if clip is None:
        raise RuntimeError("Kein aktiver Movie Clip verfügbar")

    hz = clip.size[0]  # horizontale Auflösung
    vc = clip.size[1]  # vertikale Auflösung

    ma = hz * 0.025  # margin
    md = hz * 0.025  # min_distance
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = 1  # threshold
    za = (ef * 4) / 14.0
    og = int(math.ceil(za * 1.1))  # obere Grenze
    ug = int(math.floor(za * 0.9))  # untere Grenze

    _print(f"md = {md}")
    _print(f"pz = {pz}")
    _print(f"tr = {tr}")

    return {
        'hz': hz,
        'vc': vc,
        'ma': ma,
        'md': md,
        'pz': pz,
        'sz': sz,
        'tr': tr,
        'ef': ef,
        'za': za,
        'og': og,
        'ug': ug,
    }


def run_detect_cyclus(context: bpy.types.Context, ef: int):
    """Orchestriert den Detect Cyclus Ablauf.

    1. Parameter berechnen
    2. marker_size anwenden
    3. Konsolen-Zusammenfassung
    """
    importlib.reload(helper_marker_size)
    params = compute_parameters(context, ef)
    helper_marker_size.apply_marker_size(params['pz'], params['sz'])
    print(
        f"[Kaiserlich Tracker][INFO] Detect Cyclus | hz={params['hz']} vc={params['vc']} "
        f"pz={params['pz']} sz={params['sz']} og={params['og']} ug={params['ug']} ef={params['ef']}"
    )
    return params


def _get_active_clip(context: bpy.types.Context):
    space = getattr(context, 'space_data', None)
    if space and space.type == 'CLIP_EDITOR':
        return space.clip
    return None


def _print(msg: str):
    print(f"[Kaiserlich Tracker][PARAM] {msg}")
