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
    clip = bpy.context.edit_movieclip
    if not clip:
        print('Kein Movie Clip aktiv.')
        return

    hz = clip.size[0]
    vc = clip.size[1]

    ma = hz * 0.025
    ma = hz * 0.025
    md = hz * 0.025
    print(f'ma (margin): {ma}')
    pz = int(hz * 0.01)
    print(f'pz (pixel size basis): {pz}')
    sz = pz * 2

    marker_size.calculate(pz, sz)

    tr = 1
    print(f'tr (threshold): {tr}')

    za = (ef * 4) / 14
    og = math.ceil(za * 1.1)
    ug = math.floor(za * 0.9)

    print(f'Eingabewert ef: {ef}')
    print(f'za (Zwischenwert): {za}')
    print(f'og (Obergrenze): {og}')
    print(f'ug (Untergrenze): {ug}')

    # Platzhalter für weitere Verarbeitung / Erkennung
    # ... weitere Logik kann hier implementiert werden
