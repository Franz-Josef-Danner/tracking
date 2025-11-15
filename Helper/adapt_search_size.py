# Helper/adapt_search_size.py
# ------------------------------------------------------------
# Setzt die Search-Size jedes Markers proportional zur Pattern-Size
# anhand der in Scene["calibrate_tracks"] gespeicherten Tracks.
# Basisformel: search_size = 2 * pattern_size
# ABER: effektive Search-Size im Pixelraum wird pro Achse auf max. 200 px begrenzt.
#
# pattern_size (nominal) = pattern_bound_box[1] - pattern_bound_box[0]
# search_min / search_max (nominal) werden aus der geclamp-ten Pixelgröße
# zurück in Normalized Coordinates umgerechnet.
# ------------------------------------------------------------

import bpy
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
    Berechnet die Pattern-Breite/Höhe aus pattern_bound_box (nominal).
    pattern_bound_box = ((x0, y0), (x1, y1))
    """
    try:
        bb = marker.pattern_bound_box
        x0, y0 = bb[0]
        x1, y1 = bb[1]
        size = Vector((abs(x1 - x0), abs(y1 - y0)))
        return size
    except Exception:
        return Vector((0.0, 0.0))


def _apply_search_size(marker,
                       pattern_size_nominal: Vector,
                       clip_width: float,
                       clip_height: float,
                       scale_factor: float = 2.0,
                       max_search_px: float = 200.0):
    """
    Setzt search_min / search_max relativ zum Marker.
    - pattern_size_nominal: Breite/Höhe in Normalized Coordinates.
    - Clip-Größe wird genutzt, um die effektive Pixelgröße zu berechnen.
    - Die resultierende Search-Size im Pixelraum wird pro Achse auf
      max_search_px begrenzt und dann zurück in nominale Werte umgerechnet.
    """
    if clip_width <= 0.0 or clip_height <= 0.0:
        return

    # Pattern-Größe in Pixeln
    pattern_px = Vector((
        pattern_size_nominal.x * float(clip_width),
        pattern_size_nominal.y * float(clip_height),
    ))

    # Basis-Search-Size: 2 * Pattern
    search_px = pattern_px * scale_factor

    # Pro Achse auf max_search_px clampen
    search_px.x = min(search_px.x, max_search_px)
    search_px.y = min(search_px.y, max_search_px)

    # Zurück in nominale Koordinaten
    search_size_nominal = Vector((
        search_px.x / float(clip_width),
        search_px.y / float(clip_height),
    ))

    half = search_size_nominal * 0.5

    marker.search_min = Vector((-half.x, -half.y))
    marker.search_max = Vector((+half.x, +half.y))


def adapt_search_size_for_calibrate_tracks(context):
    """
    Hauptfunktion:
    Iteriert alle Tracks in 'calibrate_tracks' und setzt Search Size
    proportional zur Pattern Size, mit hartem Cap von 200 px pro Achse.
    """
    scene = context.scene

    track_names = _load_calibrate_tracks(scene)
    if not track_names:
        return

    clip = getattr(context.space_data, "clip", None)
    if not clip or not getattr(clip, "tracking", None):
        return

    tracking = clip.tracking

    # Clip-Auflösung für Normalized↔Pixel-Umrechnung
    clip_width = float(clip.size[0])
    clip_height = float(clip.size[1])
    if clip_width <= 0.0 or clip_height <= 0.0:
        return

    total_tracks = 0
    total_markers = 0
    updated_markers = 0

    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue

        total_tracks += 1

        for mk in tr.markers:
            total_markers += 1

            if mk.mute:
                continue

            pattern_size = _compute_pattern_size(mk)
            if pattern_size.length == 0.0:
                continue

            _apply_search_size(
                mk,
                pattern_size_nominal=pattern_size,
                clip_width=clip_width,
                clip_height=clip_height,
                scale_factor=2.0,       # Deine Basisformel
                max_search_px=200.0     # Harte Obergrenze in Pixel
            )
            updated_markers += 1

    # Optional: Wenn du Logging willst, hier einbauen:
    # print(f"[AdaptSearch] Tracks: {total_tracks}, Marker: {total_markers}, aktualisiert: {updated_markers}")
