import bpy
import math
from . import marker_size

def run(context, ef: int):
    """Berechnet alle Parameter laut Vorgabe und gibt sie als Dict zurück.

    Reihenfolge / Formeln (Clip-Auflösung):
      hz = horizontale Auflösung
      vc = vertikale Auflösung
      ma = hz * 0.025 (margin)
      md = hz * 0.025 (min_distance)  -> print
      pz = hz * 0.01  (pattern size)  -> print
      sz = pz * 2     (search size)
      tr = 1          (threshold)     -> print
      ef = UI Wert
      za = (ef * 4) / 14
      og = za * 1.1
      ug = za * 0.9
    """
    scene = context.scene

    # Bestimme Auflösung: bevorzugt echte Clip-Auflösung, Fallback Render-Auflösung
    space = getattr(context, 'space_data', None)
    clip = None
    if space and getattr(space, 'type', None) == 'CLIP_EDITOR':
        clip = getattr(space, 'clip', None)
    if clip and getattr(clip, 'size', None):
        try:
            hz = int(clip.size[0])
            vc = int(clip.size[1])
        except Exception:
            hz = scene.render.resolution_x
            vc = scene.render.resolution_y
    else:
        hz = scene.render.resolution_x
        vc = scene.render.resolution_y

    ma = hz * 0.025
    md = hz * 0.025

    # pattern size (integer)
    pz = int(hz * 0.01)

    # search size (integer)
    sz = int(pz * 2)

    tr = 1

    za = (ef * 4) / 14
    # og aufrunden (ceil), ug abrunden (floor)
    og = math.ceil(za * 1.1)
    ug = math.floor(za * 0.9)

    # Delegiere Setzen der Markergrößen an marker_size Modul
    if clip:
        marker_size.apply_marker_sizes(context, pz, sz)

    # Zusammenfassung bewusst ohne direkte Ausgabe gehalten

    return {
        "ef": int(ef),
        "hz": int(hz),
        "vc": int(vc),
        "ma": int(ma),  # margin
        "md": int(md),  # min_distance
        "tr": float(tr),  # threshold
        "pz": int(pz),  # pattern size (Pixel, int)
        "sz": int(sz),  # search size (Pixel, int)
        "za": float(za),
        "og": int(og),
        "ug": int(ug),
    }
