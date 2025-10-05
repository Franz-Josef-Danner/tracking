import bpy
from .marker_size import apply_marker_sizes
import math

def run_bootstrap(context, ef: int):
  """Berechne Parameter aus Clip-Auflösung und gewünschter Markeranzahl.

  ef: Eingabewert Marker per Frame
  Formelbasis (aus Vorgabe):
    hz = horizontale Auflösung
    vc = vertikale Auflösung
    ma = margin = hz * 0.025
    md = min_distance = hz * 0.025
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = 1.0 (threshold)
    za = (ef * 4) / 14
    og = ceil(za * 1.1)
    ug = floor(za * 0.9)
  Rückgabe: dict aller relevanten Werte zur Weiterverwendung im Erkennungs-Zyklus.
  """
  clip = context.space_data.clip if getattr(context, "space_data", None) else None
  if clip is None:
    print("[Kaiserlich Tracker] Kein Clip aktiv.")
    return None

  hz = clip.size[0]
  vc = clip.size[1]

  ma = hz * 0.025
  md = hz * 0.025
  pz = int(hz * 0.01)
  sz = pz * 2
  tr = 1.0

  za = (ef * 4) / 14
  og = math.ceil(za * 1.1)  # obere Grenze Zielkorridor
  ug = math.floor(za * 0.9)  # untere Grenze Zielkorridor

  print("[Kaiserlich Tracker] ================= Bootstrap =================")
  print("[Kaiserlich Tracker] Auflösung: {}x{}".format(hz, vc))
  print(f"[Kaiserlich Tracker] margin (ma): {ma:.2f}")
  print(f"[Kaiserlich Tracker] min_distance (md): {md:.2f}")
  print(f"[Kaiserlich Tracker] pattern_size (pz): {pz}")
  print(f"[Kaiserlich Tracker] search_size (sz): {sz}")
  print(f"[Kaiserlich Tracker] threshold (tr): {tr}")
  print(f"[Kaiserlich Tracker] Eingabe (ef): {ef}")
  print(f"[Kaiserlich Tracker] Zahlenbasis (za): {za:.2f}")
  print(f"[Kaiserlich Tracker] Obergrenze (og): {og}")
  print(f"[Kaiserlich Tracker] Untergrenze (ug): {ug}")

  apply_marker_sizes(clip, pz, sz)

  return {
    "hz": hz,
    "vc": vc,
    "ma": ma,
    "md": md,
    "pz": pz,
    "sz": sz,
    "tr": tr,
    "za": za,
    "og": og,
    "ug": ug,
    "ef": ef,
  }
