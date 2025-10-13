import bpy
from .marker_size import apply_marker_sizes
import math

def run_bootstrap(context, ef: int):
  """Berechnet Start-Parameter basierend auf Clip-Auflösung und gewünschter Markeranzahl.

  Neue Vorgaben:
    se  = Szenen-Endframe (frame_end der aktiven Szene)
    hz  = horizontale Auflösung des Clips
    vc  = vertikale Auflösung des Clips
    ma  = hz * 0.025
    md  = hz * 0.025 (Wird ausgegeben)
  pz  = int(hz * 0.05) (5% der horizontalen Auflösung, ausgegeben)
    sz  = pz * 2
    tr  = 0.0001 (threshold, ausgegeben)
    ef  = Eingabewert aus UI
    za  = ef * 4
    og  = ceil(za * 1.1)
    ug  = floor(za * 0.9)

  Rückgabe: dict mit allen Parametern für den weiteren Detect-Zyklus.
  """
  clip = context.space_data.clip if getattr(context, "space_data", None) else None
  if clip is None:
    print("[Kaiserlich Tracker] Kein Clip aktiv.")
    return None

  hz = clip.size[0]
  vc = clip.size[1]
  # Szenen-Endframe (falls vorhanden)
  se = None
  if getattr(context, "scene", None) is not None:
    se = context.scene.frame_end

  ma = hz * 0.025
  md = hz * 0.025
  pz = int(hz * 0.025)
  sz = pz * 2
  tr = 0.0001
  za = ef * 4
  og = math.ceil(za * 1.1)
  ug = math.floor(za * 0.9)

  print("[Kaiserlich Tracker] ================= Bootstrap =================")
  print(f"[Kaiserlich Tracker] Auflösung: {hz}x{vc}")
  if se is not None:
    print(f"[Kaiserlich Tracker] Szenen-Endframe (se): {se}")
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
    "se": se,
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
