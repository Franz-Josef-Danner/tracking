"""Bootstrap Berechnungen gemäß Vorgaben.

Formeln:
    hz = horizontale Auflösung des Clips
    vc = vertikale Auflösung des Clips
    ma = margin = hz * 0.025
    md = min_distance = hz * 0.025
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = threshold = 1
    ef = Eingabefeld (Marker per Frame)
    za = (ef * 4) / 14
    og = ceil(za * 1.1)
    ug = floor(za * 0.9)
"""

import bpy
from . import marker_size
import math

def run(context, ef: int):
    """Führt Grundberechnungen aus und gibt ein Dict mit Werten zurück."""
    clip = bpy.context.edit_movieclip
    if not clip:
        print('Kein Movie Clip aktiv.')
        return {}

    hz = clip.size[0]
    vc = clip.size[1]

    ma = hz * 0.025  # margin
    md = hz * 0.025  # min_distance
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = 1  # threshold konstant laut Vorgabe

    marker_size.apply(pz, sz)

    za = (ef * 4) / 14
    og = math.ceil(za * 1.1)
    ug = math.floor(za * 0.9)

    print(f'hz: {hz}  vc: {vc}')
    print(f'ma (margin): {ma}')
    print(f'md (min_distance): {md}')
    print(f'pz (pattern size basis): {pz}')
    print(f'sz (search size): {sz}')
    print(f'tr (threshold): {tr}')
    print(f'ef (Eingabe): {ef}')
    print(f'za: {za}  og: {og}  ug: {ug}')

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
