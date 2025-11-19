# Helper/bootstrap.py
# ---------------------------------------------------------------------
import bpy
import math

from .marker_size import apply_marker_sizes


def run_bootstrap(context, ef: int):
    """Berechnet Startparameter basierend auf Clip-Auflösung und gewünschter Markeranzahl.

    Parameter:
        ef: gewünschte Markeranzahl (aus UI)
    Rückgabe:
        dict mit allen Startparametern für den Detect-Zyklus.
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        return None

    hz = clip.size[0]
    vc = clip.size[1]

    se = None
    if getattr(context, "scene", None) is not None:
        se = context.scene.frame_end

    # Basis-Parameter
    ma = hz * 0.025          # max area
    md = hz * 0.025          # min distance
    pz = int(hz * 0.01)      # pattern size
    sz = pz * 2              # search size
    tr = 0.0001              # threshold
    za = ef * 4              # Zielanzahl intern
    og = math.ceil(za * 1.1) # Obergrenze
    ug = math.floor(za * 0.9)# Untergrenze

    # Neue Defaults
    default_correlation_min = 0.97
    default_margin = sz

    apply_marker_sizes(clip, pz, sz)

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



    return params


def apply_bootstrap_defaults(context, params: dict) -> None:
    """
    Übernimmt die aus run_bootstrap() berechneten Werte in:
      - Scene-Properties (z.B. kaiserlich_correlation_min, kaiserlich_margin)
      - Tracking-Settings (settings.correlation_min)
      - Scene-ID-Property "bootstrap_params"

    Erwartet das dict, das von run_bootstrap() zurückgegeben wurde.
    """
    if not params:
        return

    scene = getattr(context, "scene", None)
    if scene is None:
        return

    # Aktiven Clip ermitteln
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    if clip is None:
        clip = getattr(scene.tracking, "active", None)

    corr = float(params.get("default_correlation_min", 0.95))
    margin = int(params.get("default_margin", 0))

    # --- Scene-Properties ----------------------------------------------------
    if hasattr(scene, "kaiserlich_correlation_min"):
        scene.kaiserlich_correlation_min = corr
    else:
        print("[BootstrapApply] Scene-Property 'kaiserlich_correlation_min' nicht vorhanden
    if hasattr(scene, "kaiserlich_margin"):
        scene.kaiserlich_margin = margin
    else:
        print("[BootstrapApply] Scene-Property 'kaiserlich_margin' nicht vorhanden")
    # --- Tracking-Settings: default_correlation_min --------------------------
    if clip is not None:
        try:
            settings = clip.tracking.settings

            old_val = settings.default_correlation_min
            settings.default_correlation_min = corr
            new_val = settings.default_correlation_min


        except Exception as e:
            print(f"[BootstrapApply] FEHLER beim Setzen von settings.default_correlation_min: {e}")
    else:
        print("[BootstrapApply] Kein Clip gefunden – Tracking-Settings werden nicht gesetzt.")

    # --- Params in Scene-ID-Property speichern ------------------------------
    try:
        scene["bootstrap_params"] = dict(params)
    except Exception as e:
        print(f"[BootstrapApply] FEHLER beim Setzen von scene['bootstrap_params']: {e}")