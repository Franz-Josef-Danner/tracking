# Helper/threshold_stats.py
import bpy

# -------------------------------------------------------------------
# Sicherstellen, dass die Scene-Properties existieren
# Wird nur einmal pro Add-on-Initialisierung benötigt,
# schadet aber nicht wenn mehrfach ausgeführt.
# -------------------------------------------------------------------
def ensure_threshold_properties(scene: bpy.types.Scene):

    defaults = {
        "kaiserlich_rot_x_min": float("inf"),
        "kaiserlich_rot_x_max": float("-inf"),
        "kaiserlich_rot_y_min": float("inf"),
        "kaiserlich_rot_y_max": float("-inf"),

        "kaiserlich_scale_min_min": float("inf"),
        "kaiserlich_scale_min_max": float("-inf"),
        "kaiserlich_scale_max_min": float("inf"),
        "kaiserlich_scale_max_max": float("-inf"),

        "kaiserlich_rot_scale_rot_min": float("inf"),
        "kaiserlich_rot_scale_rot_max": float("-inf"),
        "kaiserlich_rot_scale_scale_min": float("inf"),
        "kaiserlich_rot_scale_scale_max": float("-inf"),

        "kaiserlich_persp_min": float("inf"),
        "kaiserlich_persp_max": float("-inf"),
    }

    for key, value in defaults.items():
        if key not in scene:
            scene[key] = value


# -------------------------------------------------------------------
# Hauptfunktion: Thresholds lesen und Min/Max updaten
# -------------------------------------------------------------------
def update_threshold_extrema(scene: bpy.types.Scene):
    """
    Liest die UI-Thresholds aus und speichert permanent die
    höchsten und tiefsten jemals beobachteten Werte pro Kategorie.
    """

    ensure_threshold_properties(scene)

    # --- Werte aus UI ---
    rot_x = scene.kaiserlich_rot_thresh_x
    rot_y = scene.kaiserlich_rot_thresh_y

    scale_min = scene.kaiserlich_scale_thresh_min
    scale_max = scene.kaiserlich_scale_thresh_max

    rot_scale_rot = scene.kaiserlich_rot_scale_thresh_rot
    rot_scale_scale = scene.kaiserlich_rot_scale_thresh_scale

    persp = scene.kaiserlich_perspective_thresh

    # --- Min/Max Aktualisierung ---
    # Rotation X
    scene["kaiserlich_rot_x_min"] = min(scene["kaiserlich_rot_x_min"], rot_x)
    scene["kaiserlich_rot_x_max"] = max(scene["kaiserlich_rot_x_max"], rot_x)

    # Rotation Y
    scene["kaiserlich_rot_y_min"] = min(scene["kaiserlich_rot_y_min"], rot_y)
    scene["kaiserlich_rot_y_max"] = max(scene["kaiserlich_rot_y_max"], rot_y)

    # Scale Min
    scene["kaiserlich_scale_min_min"] = min(scene["kaiserlich_scale_min_min"], scale_min)
    scene["kaiserlich_scale_min_max"] = max(scene["kaiserlich_scale_min_max"], scale_min)

    # Scale Max
    scene["kaiserlich_scale_max_min"] = min(scene["kaiserlich_scale_max_min"], scale_max)
    scene["kaiserlich_scale_max_max"] = max(scene["kaiserlich_scale_max_max"], scale_max)

    # Rot+Scale Rot
    scene["kaiserlich_rot_scale_rot_min"] = min(scene["kaiserlich_rot_scale_rot_min"], rot_scale_rot)
    scene["kaiserlich_rot_scale_rot_max"] = max(scene["kaiserlich_rot_scale_rot_max"], rot_scale_rot)

    # Rot+Scale Scale
    scene["kaiserlich_rot_scale_scale_min"] = min(scene["kaiserlich_rot_scale_scale_min"], rot_scale_scale)
    scene["kaiserlich_rot_scale_scale_max"] = max(scene["kaiserlich_rot_scale_scale_max"], rot_scale_scale)

    # Perspective
    scene["kaiserlich_persp_min"] = min(scene["kaiserlich_persp_min"], persp)
    scene["kaiserlich_persp_max"] = max(scene["kaiserlich_persp_max"], persp)


# -------------------------------------------------------------------
# Logging-Funktion
# -------------------------------------------------------------------
def log_threshold_extrema(scene: bpy.types.Scene):
    """
    Gibt alle min/max Threshold-Werte als geordnetes Log aus.
    """

    ensure_threshold_properties(scene)

    print("\n================ Threshold Extremwerte ================")
    print(f"[Rotation] ΔX: min={scene['kaiserlich_rot_x_min']:.6f}  "
          f"max={scene['kaiserlich_rot_x_max']:.6f}")
    print(f"[Rotation] ΔY: min={scene['kaiserlich_rot_y_min']:.6f}  "
          f"max={scene['kaiserlich_rot_y_max']:.6f}")

    print(f"[Scale Min]  min={scene['kaiserlich_scale_min_min']:.6f}  "
          f"max={scene['kaiserlich_scale_min_max']:.6f}")
    print(f"[Scale Max]  min={scene['kaiserlich_scale_max_min']:.6f}  "
          f"max={scene['kaiserlich_scale_max_max']:.6f}")

    print(f"[LocRotScale Rot]   min={scene['kaiserlich_rot_scale_rot_min']:.6f}  "
          f"max={scene['kaiserlich_rot_scale_rot_max']:.6f}")
    print(f"[LocRotScale Scale] min={scene['kaiserlich_rot_scale_scale_min']:.6f}  "
          f"max={scene['kaiserlich_rot_scale_scale_max']:.6f}")

    print(f"[Perspective] min={scene['kaiserlich_persp_min']:.6f}  "
          f"max={scene['kaiserlich_persp_max']:.6f}")
    print("========================================================\n")
