# Helper/bootstrap.py
# ---------------------------------------------------------------------
import bpy
from .marker_size import apply_marker_sizes
import math

def run_bootstrap(context, ef: int):
    """Berechnet Startparameter basierend auf Clip-Auflösung und gewünschter Markeranzahl.

    Parameter:
        ef: gewünschte Markeranzahl (aus UI)
    Rückgabe:
        dict mit allen Startparametern für den Detect-Zyklus.
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        print("[Bootstrap] ABBRUCH: Kein aktiver Clip gefunden (context.space_data.clip ist None).")
        return None

    hz = clip.size[0]
    vc = clip.size[1]

    se = None
    if getattr(context, "scene", None) is not None:
        se = context.scene.frame_end

    print("[Bootstrap] --------------------------------------------------")
    print(f"[Bootstrap] Clip: {getattr(clip, 'name', '<ohne Name>')}")
    print(f"[Bootstrap] Auflösung (hz x vc): {hz} x {vc}")
    print(f"[Bootstrap] frame_end (se): {se}")
    print(f"[Bootstrap] gewünschte Markeranzahl (ef): {ef}")

    ma = hz * 0.025
    md = hz * 0.025
    pz = int(hz * 0.01)
    sz = pz * 2
    tr = 0.0001
    za = ef * 4
    og = math.ceil(za * 1.1)
    ug = math.floor(za * 0.9)

    # Neue Defaults
    default_correlation_min = 0.79
    default_margin = sz

    print("[Bootstrap] Berechnete Parameter:")
    print(f"  ma (max area)           : {ma}")
    print(f"  md (min distance)       : {md}")
    print(f"  pz (pattern_size)       : {pz}")
    print(f"  sz (search_size)        : {sz}")
    print(f"  tr (threshold)          : {tr}")
    print(f"  za (Zielanzahl intern)  : {za}")
    print(f"  og (Obergrenze)         : {og}")
    print(f"  ug (Untergrenze)        : {ug}")
    print(f"  default_correlation_min : {default_correlation_min}")
    print(f"  default_margin          : {default_margin}")

    print("[Bootstrap] wende apply_marker_sizes(...) an ...")
    apply_marker_sizes(clip, pz, sz)
    print("[Bootstrap] apply_marker_sizes abgeschlossen.")

    params = {
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
        "default_correlation_min": default_correlation_min,
        "default_margin": default_margin,
    }

    print("[Bootstrap] RETURN Params:")
    for k, v in params.items():
        print(f"  {k:>24} : {v}")
    print("[Bootstrap] --------------------------------------------------")

    return params
