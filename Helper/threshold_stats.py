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


def reset_threshold_extrema(scene: bpy.types.Scene):
    """
    Setzt alle gespeicherten Min/Max-Werte zurück.
    """
    keys = [
        "kaiserlich_rot_x_min", "kaiserlich_rot_x_max",
        "kaiserlich_rot_y_min", "kaiserlich_rot_y_max",

        "kaiserlich_scale_min_min", "kaiserlich_scale_min_max",
        "kaiserlich_scale_max_min", "kaiserlich_scale_max_max",

        "kaiserlich_rot_scale_rot_min", "kaiserlich_rot_scale_rot_max",
        "kaiserlich_rot_scale_scale_min", "kaiserlich_rot_scale_scale_max",

        "kaiserlich_persp_min", "kaiserlich_persp_max",
    ]

    for k in keys:
        if "min" in k:
            scene[k] = float("inf")
        else:
            scene[k] = float("-inf")

    # logging entfernt

# -------------------------------------------------------
# Interner Helper: Extremwerte updaten (mit 0/1-Ignore)
# -------------------------------------------------------
def _update_extrema(scene: bpy.types.Scene, min_key: str, max_key: str, value: float) -> None:

    scene[min_key] = min(scene[min_key], value)
    scene[max_key] = max(scene[max_key], value)


def update_threshold_extrema(scene: bpy.types.Scene):
    """
    Liest die UI-Thresholds aus und speichert permanent die
    höchsten und tiefsten jemals beobachteten Werte pro Kategorie.
    Werte genau 0 oder 1 werden ignoriert.
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

    # --- Min/Max Aktualisierung mit 0/1-Ignore ---
    _update_extrema(scene, "kaiserlich_rot_x_min", "kaiserlich_rot_x_max", rot_x)
    _update_extrema(scene, "kaiserlich_rot_y_min", "kaiserlich_rot_y_max", rot_y)

    _update_extrema(scene, "kaiserlich_scale_min_min", "kaiserlich_scale_min_max", scale_min)
    _update_extrema(scene, "kaiserlich_scale_max_min", "kaiserlich_scale_max_max", scale_max)

    _update_extrema(scene, "kaiserlich_rot_scale_rot_min", "kaiserlich_rot_scale_rot_max", rot_scale_rot)
    _update_extrema(scene, "kaiserlich_rot_scale_scale_min", "kaiserlich_rot_scale_scale_max", rot_scale_scale)

    _update_extrema(scene, "kaiserlich_persp_min", "kaiserlich_persp_max", persp)


# -------------------------------------------------------------------
# Logging-Funktion
# -------------------------------------------------------------------
def log_threshold_extrema(scene: bpy.types.Scene):
    """
    Gibt alle min/max Threshold-Werte als geordnetes Log aus.
    """

    ensure_threshold_properties(scene)

        # logging entfernt
