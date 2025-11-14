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
from mathutils import Vector


def _load_calibrate_tracks(scene):
    """
    Lädt die Liste der Kalibrations-Track-Namen aus scene['calibrate_tracks']
    """
    try:
        s = scene.get("calibrate_tracks", "")
        if not s:
            print("[AdaptSearch] Keine 'calibrate_tracks' in Scene gefunden oder leer.")
            return []
        names = [t.strip() for t in s.split(",") if t.strip()]
        print(f"[AdaptSearch] Geladene calibrate_tracks: {names}")
        return names
    except Exception as e:
        print(f"[AdaptSearch] FEHLER beim Laden von 'calibrate_tracks': {e}")
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
        size = Vector((abs(x1 - x0), abs(y1 - y0)))
        return size
    except Exception as e:
        print(f"[AdaptSearch] FEHLER beim Lesen von pattern_bound_box: {e}")
        return Vector((0.0, 0.0))


def _apply_search_size(marker, pattern_size: Vector, scale_factor: float = 2.0):
    """
    Setzt search_min / search_max relativ zum Marker.
    """
    size = pattern_size * scale_factor
    half = size * 0.5

    marker.search_min = Vector((-half.x, -half.y))
    marker.search_max = Vector((+half.x, +half.y))


def adapt_search_size_for_calibrate_tracks(context):
    """
    Hauptfunktion:
    Iteriert alle Tracks in 'calibrate_tracks' und setzt Search Size
    proportional zur Pattern Size.
    """
    scene = context.scene
    print("[AdaptSearch] =============================================")
    print("[AdaptSearch] Starte Anpassung der Search Size für calibrate_tracks ...")

    track_names = _load_calibrate_tracks(scene)
    if not track_names:
        print("[AdaptSearch] Abbruch: Keine Track-Namen vorhanden.")
        print("[AdaptSearch] =============================================")
        return

    clip = getattr(context.space_data, "clip", None)
    if not clip or not getattr(clip, "tracking", None):
        print("[AdaptSearch] Abbruch: Kein aktiver Clip oder kein Tracking verfügbar.")
        print("[AdaptSearch] =============================================")
        return

    print(f"[AdaptSearch] Aktiver Clip: {getattr(clip, 'name', '<ohne Name>')}")
    tracking = clip.tracking

    total_tracks = 0
    total_markers = 0
    updated_markers = 0

    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            print(f"[AdaptSearch] WARNUNG: Track '{name}' nicht im Clip gefunden.")
            continue

        total_tracks += 1
        print(f"[AdaptSearch] Verarbeite Track: '{tr.name}' (Marker: {len(tr.markers)})")

        for mk in tr.markers:
            total_markers += 1

            if mk.mute:
                print(f"[AdaptSearch]   Marker auf Frame {mk.frame} ist gemutet → übersprungen.")
                continue

            pattern_size = _compute_pattern_size(mk)
            if pattern_size.length == 0.0:
                print(f"[AdaptSearch]   Marker Frame {mk.frame}: Pattern-Size = 0 → keine Anpassung.")
                continue

            _apply_search_size(mk, pattern_size, scale_factor=2.0)
            updated_markers += 1

            print(
                f"[AdaptSearch]   Marker Frame {mk.frame}: "
                f"PatternSize = ({pattern_size.x:.6f}, {pattern_size.y:.6f}) → "
                f"SearchMin = ({mk.search_min.x:.6f}, {mk.search_min.y:.6f}), "
                f"SearchMax = ({mk.search_max.x:.6f}, {mk.search_max.y:.6f})"
            )

    print("[AdaptSearch] -------------------------------------------------")
    print(f"[AdaptSearch] Tracks gefunden:       {total_tracks}")
    print(f"[AdaptSearch] Marker gesamt:         {total_markers}")
    print(f"[AdaptSearch] Marker angepasst:      {updated_markers}")
    print("[AdaptSearch] Anpassung der Search Size abgeschlossen.")
    print("[AdaptSearch] =============================================")
