# Helper/adapt_search_size.py
# ------------------------------------------------------------
# Setzt die Search-Size jedes Markers proportional zur Pattern-Size
# anhand der in Scene["calibrate_tracks"] gespeicherten Tracks.
# Basisformel (Fallback): search_size = 2 * pattern_size
# ABER:
#   1) Primäre Größe kommt aus der gemessenen Bewegung (F → F+2)
#      von Referenz-Tracks in der Nähe.
#   2) Die bisherige Pattern-basierte Größe dient als Minimum.
#   3) effektive Search-Size im Pixelraum wird pro Achse auf max. 200 px begrenzt.
#
# pattern_size (nominal) = pattern_bound_box[1] - pattern_bound_box[0]
# search_min / search_max (nominal) werden aus der geclamp-ten Pixelgröße
# zurück in Normalized Coordinates umgerechnet.
# ------------------------------------------------------------

import bpy
from mathutils import Vector


def _load_calibrate_tracks(scene) -> list:
    """
    Lädt die Liste der Kalibrations-Track-Namen.
    Unterstützt:
      1) scene['calibrate_tracks'] als echte Python-Liste
      2) scene['calibrate_tracks'] als kommaseparierter String (Legacy)
    """
    val = scene.get("calibrate_tracks", None)
    if not val:
        return []

    # === Fall 1: Neue Speicherung als Liste ===
    if isinstance(val, (list, tuple)):
        # nur Strings/Ints zulassen
        return [str(t).strip() for t in val if isinstance(t, (str, int))]

    # === Fall 2: Legacy-String ===
    if isinstance(val, str):
        parts = [t.strip() for t in val.split(",") if t.strip()]
        return parts

    # === Fallback ===
    try:
        # z. B. wenn jemand fälschlich einen anderen Typ speichert
        return [str(x).strip() for x in list(val)]
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


def _get_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    """Sucht einen Marker exakt am angegebenen Frame (ohne Blender-spezifische find_frame-API vorauszusetzen)."""
    for mk in track.markers:
        try:
            if mk.frame == frame:
                return mk
        except Exception:
            continue
    return None


def _apply_search_size(
    marker,
    pattern_size_nominal: Vector,
    clip_width: float,
    clip_height: float,
    scale_factor: float = 2.0,
    max_search_px: float = 200.0,
    motion_search_px: Vector | None = None,
):
    """
    Setzt search_min / search_max relativ zum Marker.

    - pattern_size_nominal: Breite/Höhe in Normalized Coordinates.
    - Clip-Größe wird genutzt, um die effektive Pixelgröße zu berechnen.
    - Die resultierende Search-Size im Pixelraum wird pro Achse auf
      max_search_px begrenzt.

    NEU:
    - motion_search_px: Search-Size in Pixel (X/Y) basierend auf
      gemessener Bewegung. Pro Achse wird:
          search_px = max(fallback_px, motion_search_px)
      verwendet. Fehlt motion_search_px, gilt nur der Fallback.
    """
    if clip_width <= 0.0 or clip_height <= 0.0:
        return

    # Pattern-Größe in Pixeln
    pattern_px = Vector((
        pattern_size_nominal.x * float(clip_width),
        pattern_size_nominal.y * float(clip_height),
    ))

    # Fallback-Search-Size: 2 * Pattern
    fallback_px = pattern_px * scale_factor

    # Fallback zunächst auf max_search_px clampen
    fallback_px.x = min(fallback_px.x, max_search_px)
    fallback_px.y = min(fallback_px.y, max_search_px)

    # Wenn Bewegungs-basierte Search-Size vorhanden ist:
    if motion_search_px is not None:
        # Pro Achse das Maximum aus Fallback und Bewegungswert verwenden
        search_px = Vector((
            max(fallback_px.x, motion_search_px.x),
            max(fallback_px.y, motion_search_px.y),
        ))
    else:
        search_px = fallback_px

    # Abschließend nochmal auf max_search_px clampen (Sicherheit)
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
    Iteriert alle Tracks in 'calibrate_tracks' und setzt die Search Size
    im aktuellen Frame wie folgt:

    1) Finde Referenz-Tracks:
       - Marker im Frame F, F+1, F+2 vorhanden
       - Marker und Track nicht gemuted/disabled

    2) Berechne für jeden Referenz-Track die Distanz:
           dist = |pos(F+2) - pos(F)|  (in Normalized Coordinates)

    3) Für jeden Kalibrations-Marker im aktuellen Frame F:
       - Finde die 3 nächstgelegenen Referenz-Tracks anhand der
         Position im Frame F.
       - Berechne den Mittelwert der dist-Werte dieser 3
         Referenz-Tracks → avg_move (normalized).

       - Wandle avg_move in Pixelraum um (Option 4):
           motion_search_px.x = avg_move * clip_width
           motion_search_px.y = avg_move * clip_height

       - Übergib motion_search_px an _apply_search_size, das
         pro Achse:
             search_px_axis = max(fallback_px_axis, motion_px_axis)
         verwendet und auf max_search_px clampet.

    4) Falls keine Referenz-Tracks oder keine brauchbaren Daten
       vorhanden sind, wird nur die bisherige Pattern-basierte
       Fallback-Größe verwendet.
    """
    scene = context.scene
    current_frame = scene.frame_current

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

    frame_f = current_frame
    frame_f1 = current_frame + 1
    frame_f2 = current_frame + 2

    # ------------------------------------------------------------
    # Schritt 1: Referenz-Tracks sammeln
    # ------------------------------------------------------------
    ref_entries = []  # Liste von Dicts mit: track, pos_f, dist_f_to_f2

    for tr in tracking.tracks:
        try:
            if getattr(tr, "mute", False):
                continue
        except Exception:
            # wenn Track kein mute-Attribut hat, ignoriere das Flag
            pass

        mk_f = _get_marker_at_frame(tr, frame_f)
        mk_f1 = _get_marker_at_frame(tr, frame_f1)
        mk_f2 = _get_marker_at_frame(tr, frame_f2)

        if not mk_f or not mk_f1 or not mk_f2:
            continue

        # Marker-Zustand prüfen (nicht gemuted/disabled)
        if getattr(mk_f, "mute", False) or getattr(mk_f1, "mute", False) or getattr(mk_f2, "mute", False):
            continue

        # Optional: is_valid berücksichtigen, wenn vorhanden
        if getattr(mk_f, "is_valid", True) is False:
            continue
        if getattr(mk_f1, "is_valid", True) is False:
            continue
        if getattr(mk_f2, "is_valid", True) is False:
            continue

        try:
            pos_f = Vector(mk_f.co)
            pos_f2 = Vector(mk_f2.co)
        except Exception:
            continue

        dist = (pos_f2 - pos_f).length
        if dist <= 0.0:
            # Nullbewegungen bringen für Maßfindung wenig, aber man
            # könnte sie theoretisch zulassen. Hier filtern wir sie aus.
            continue

        ref_entries.append({
            "track": tr,
            "pos_f": pos_f,
            "dist": dist,
        })

    # Wenn es keine Referenzdaten gibt, bleiben wir voll im Fallback-Modus
    has_refs = len(ref_entries) > 0

    total_tracks = 0
    total_markers = 0
    updated_markers = 0

    # ------------------------------------------------------------
    # Schritt 2: Kalibrations-Tracks verarbeiten (nur Marker im F)
    # ------------------------------------------------------------
    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue

        total_tracks += 1

        for mk in tr.markers:
            total_markers += 1

            # Nur Marker im aktuellen Frame berücksichtigen
            try:
                if mk.frame != current_frame:
                    continue
            except Exception:
                continue

            if getattr(mk, "mute", False):
                continue

            pattern_size = _compute_pattern_size(mk)
            # Ohne Pattern-Größe macht Fallback keinen Sinn,
            # aber Bewegungs-basierte Größe könnte theoretisch
            # trotzdem verwendet werden – wir erlauben beides.
            if pattern_size.length == 0.0 and not has_refs:
                # Weder Pattern, noch Referenzen → nichts zu tun.
                continue

            motion_search_px = None

            # ------------------------------------------------
            # Bewegungsbasierte Search-Size bestimmen (wenn möglich)
            # ------------------------------------------------
            if has_refs:
                try:
                    marker_pos_f = Vector(mk.co)
                except Exception:
                    marker_pos_f = None

                if marker_pos_f is not None:
                    # Distanzen zu allen Referenz-Markern im Frame F
                    distances = []
                    for entry in ref_entries:
                        d = (entry["pos_f"] - marker_pos_f).length
                        distances.append((d, entry))

                    if distances:
                        # Sortieren nach Distanz, die 3 nächsten wählen
                        distances.sort(key=lambda x: x[0])
                        nearest = [e for (_, e) in distances[:3]]

                        if nearest:
                            avg_move = sum(e["dist"] for e in nearest) / float(len(nearest))
                            if avg_move > 0.0:
                                # Option 4: getrennte Skalierung X/Y
                                motion_search_px = Vector((
                                    avg_move * clip_width,
                                    avg_move * clip_height,
                                ))

            # ------------------------------------------------
            # Search-Size anwenden:
            # - Pattern-basiert = Fallback
            # - Bewegungs-basiert = Zusatz, der Fallback nicht unterschreiten darf
            # ------------------------------------------------
            _apply_search_size(
                mk,
                pattern_size_nominal=pattern_size,
                clip_width=clip_width,
                clip_height=clip_height,
                scale_factor=2.0,       # Fallback-Basisformel
                max_search_px=200.0,    # Harte Obergrenze in Pixel
                motion_search_px=motion_search_px,
            )
            updated_markers += 1

    # Optionales Logging (bei Bedarf einkommentieren)
    # print(f"[AdaptSearch] Referenz-Tracks: {len(ref_entries)}, "
    #       f"Calibrate-Tracks: {total_tracks}, "
    #       f"Marker (gesamt): {total_markers}, "
    #       f"aktualisiert (Frame {current_frame}): {updated_markers}")