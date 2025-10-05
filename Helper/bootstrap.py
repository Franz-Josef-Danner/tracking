import bpy
from .marker_size import apply_marker_sizes
import math

def run_bootstrap(context, ef: int):
    """
    ef: Eingabewert Marker per Frame
    Berechnet Parameter gemäß Vorgabe:
      hz = horizontale Auflösung
      vc = vertikale Auflösung
      ma = margin = hz * 0.025
      md = min_distance = hz * 0.025
      pz = int(hz * 0.01)
      sz = pz * 2
      tr = 1 (threshold)
      za = (ef * 4) / 14
      og = ceil(za * 1.1)
      ug = floor(za * 0.9)
    Gibt Debug-Ausgaben in die Konsole und setzt Standard Marker Größen.
    """
    clip = context.space_data.clip if context.space_data else None
    if clip is None:
        print("[Kaiserlich Tracker] Kein Clip aktiv.")
        return

    hz = clip.size[0]
    vc = clip.size[1]

    ma = hz * 0.025
    md = hz * 0.025
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = 1

    za = (ef * 4) / 14
    og = math.ceil(za * 1.1)
    ug = math.floor(za * 0.9)

    print("[Kaiserlich Tracker] Auflösung: {}x{}".format(hz, vc))
    print(f"margin (ma): {ma}")
    print(f"min_distance (md): {md}")
    print(f"pattern_size (pz): {pz}")
    print(f"search_size (sz): {sz}")
    print(f"threshold (tr): {tr}")
    print(f"Eingabe (ef): {ef}")
    print(f"Zahlenbasis (za): {za}")
    print(f"Obergrenze (og): {og}")
    print(f"Untergrenze (ug): {ug}")

    apply_marker_sizes(clip, pz, sz)
