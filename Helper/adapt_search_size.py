# Helper/adapt_search_size.py
# ------------------------------------------------------------
# Setzt Search-Size proportional zur Pattern-Size,
# aber mit harter Obergrenze: max. 200 Pixel pro Achse.
# ------------------------------------------------------------

import bpy
from mathutils import Vector

MAX_SEARCH_PX = 200.0


def _load_calibrate_tracks(scene):
    try:
        s = scene.get("calibrate_tracks", "")
        if not s:
            return []
        return [t.strip() for t in s.split(",") if t.strip()]
    except Exception:
        return []


def _compute_pattern_size(marker) -> Vector:
    try:
        bb = marker.pattern_bound_box
        x0, y0 = bb[0]
        x1, y1 = bb[1]
        return Vector((abs(x1 - x0), abs(y1 - y0)))
    except Exception:
        return Vector((0.0, 0.0))


def _clamp_search_size(size: Vector) -> Vector:
    """
    Begrenzung auf maximal +- MAX_SEARCH_PX relativ zum Marker.
    """
    # Die Search-Size beschreibt die unnormierte Pixelgröße,
    # wobei Blender hier einen normierten Vektor speichert.
    #
    # Wir begrenzen direkt den Wert der Search-Box (in px-Äquivalent):
    clamped_x = min(size.x, MAX_SEARCH_PX)
    clamped_y = min(size.y, MAX_SEARCH_PX)
    return Vector((clamped_x, clamped_y))


def _apply_search_size(marker, pattern_size: Vector, scale_factor: float = 2.0):
    """
    Setzt search_min / search_max mit max. 200px Limit.
    """
    size = pattern_size * scale_factor
    size = _clamp_search_size(size)
    half = size * 0.5

    marker.search_min = Vector((-half.x, -half.y))
    marker.search_max = Vector((+half.x, +half.y))


def adapt_search_size_for_calibrate_tracks(context):
    """
    Hauptfunktion:
    Iteriert alle Tracks in 'calibrate_tracks' und setzt Search Size
    proportional zur Pattern Size mit Max-Limit.
    """
    scene = context.scene

    track_names = _load_calibrate_tracks(scene)
    if not track_names:
        return

    clip = getattr(context.space_data, "clip", None)
    if not clip or not getattr(clip, "tracking", None):
        return

    tracking = clip.tracking

    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue

        for mk in tr.markers:
            if mk.mute:
                continue

            pattern_size = _compute_pattern_size(mk)
            if pattern_size.length == 0.0:
                continue

            _apply_search_size(mk, pattern_size, scale_factor=2.0)
