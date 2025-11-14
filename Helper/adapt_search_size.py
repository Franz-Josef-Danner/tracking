# Helper/adapt_search_size.py
# ------------------------------------------------------------
# Setzt die Search-Size jedes Markers proportional zur Pattern-Size
# anhand der in Scene["calibrate_tracks"] gespeicherten Tracks.
# Formel: search_size = 2 * pattern_size
#
# pattern_size = pattern_bound_box[1] - pattern_bound_box[0]
# search_min  = (-search_size.x/2, -search_size.y/2)
# search_max  = (+search_size.x/2, +search_size.y/2)
# ------------------------------------------------------------

import bpy
import ast
from mathutils import Vector


def _load_calibrate_tracks(scene):
    """
    Lädt die Liste der Kalibrations-Track-Namen aus scene['calibrate_tracks']
    """
    try:
        s = scene.get("calibrate_tracks", "")
        if not s:
            return []
        names = [t.strip() for t in s.split(",") if t.strip()]
        return names
    except Exception:
        return []


def _compute_pattern_size(marker) -> Vector:
    """
    Berechnet die Pattern-Breite/Höhe aus pattern_bound_box.
    pattern_bound_box = ((x0, y0), (x1, y1))
    """
    try:
        bb = marker.pattern_bound_box
        x0, y0 = bb[0]
        x1, y1 = bb[1]
        return Vector((abs(x1 - x0), abs(y1 - y0)))
    except Exception:
        return Vector((0.0, 0.0))


def _apply_search_size(marker, pattern_size: Vector, scale_factor: float = 2.0):
    """
    Setzt search_min / search_max relativ zum Marker.
    """
    size = pattern_size * scale_factor

    # Suchbereich um den Marker-Zentrum herum aufspannen
    half = size * 0.5

    # Normalisiert relativ zum Marker
    marker.search_min = Vector((-half.x, -half.y))
    marker.search_max = Vector((+half.x, +half.y))


def adapt_search_size_for_calibrate_tracks(context):
    """
    Hauptfunktion:
    Iteriert alle Tracks in 'calibrate_tracks' und setzt Search Size
    proportional zur Pattern Size.
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

        # Über alle Marker iterieren
        for mk in tr.markers:
            if mk.mute:
                continue

            pattern_size = _compute_pattern_size(mk)

            # Nur setzen, wenn Pattern gültig
            if pattern_size.length == 0.0:
                continue

            _apply_search_size(mk, pattern_size, scale_factor=2.0)
