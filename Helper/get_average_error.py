# Helper/get_average_error.py
import bpy
from math import isnan


def _safe_error_value(err) -> float:
    """Konvertiert einen Error-Wert robust nach float.
    Fällt auf 0.0 zurück, wenn der Wert nicht existiert oder unbrauchbar ist.
    Wird nur für die Fallback-Reconstruction verwendet.
    """
    if err is None:
        return 0.0
    try:
        value = float(err)
    except (TypeError, ValueError):
        return 0.0

    if isnan(value) or value < 0.0:
        return 0.0

    return value


def _get_tracks_for_solve(tracking: bpy.types.MovieTracking,
                          object_name: str | None):
    """Liefert die relevanten Tracks für Kamera- oder Object-Solve."""
    if object_name:
        mobj = tracking.objects.get(object_name)
        if mobj is None:
            return []
        return list(mobj.tracks)
    else:
        return list(tracking.tracks)


def _compute_weighted_average_error(tracks) -> float:
    """Berechnet den gewichteten Durchschnitts-Error über alle Tracks.

    Formel:
        error[i]       = average_error des Tracks (wenn < 0 oder NaN → ignorieren)
        track_len[i]   = effektive Tracklänge (Anzahl nicht gemuteter Marker)
        anteil[i]      = error[i] * track_len[i]
        gesamtlänge    = Summe aller track_len[i]
        gesamtanteile  = Summe aller anteil[i]
        avg_error      = gesamtanteile / gesamtlänge

    Rückgabe:
        float: gewichteter Durchschnitts-Error; 0.0 wenn keine gültigen Tracks.
    """
    total_weight = 0.0      # gesamtlänge
    total_weighted = 0.0    # gesamtanteile

    for track in tracks:
        # 1) Error-Wert holen und prüfen
        raw_err = getattr(track, "average_error", None)
        if raw_err is None:
            continue

        try:
            err = float(raw_err)
        except (TypeError, ValueError):
            continue

        if isnan(err) or err < 0.0:
            # Ungültig laut Spezifikation → Track komplett ignorieren
            continue

        # 2) Track-Länge bestimmen (nur nicht gemutete Marker zählen)
        markers = getattr(track, "markers", None)
        if not markers:
            continue

        track_len = 0
        for m in markers:
            # Nur Marker, die nicht gemutet sind
            if getattr(m, "mute", False):
                continue
            track_len += 1

        if track_len <= 0:
            # Track ohne verwertbare Marker → ignorieren
            continue

        # 3) Gewichtung aufsummieren
        total_weight += track_len
        total_weighted += err * track_len

    if total_weight <= 0.0:
        return 0.0

    return total_weighted / total_weight


def get_average_error(clip: bpy.types.MovieClip | None = None,
                      object_name: str | None = None) -> float:
    """
    Liefert den durchschnittlichen Solve-Fehler in Pixeln.

    Priorität:
    1) Gewichteter Durchschnitt aller Track-Errors (average_error je Track),
       gewichtet mit Tracklänge (Anzahl nicht gemuteter Marker).
       Ungültige Errors (None, NaN, < 0) werden komplett ignoriert.
    2) Fallback auf Blenders Reconstruction-average_error (Object oder Camera),
       falls keine gültigen Tracks vorhanden sind.
    3) Fallback 0.0, wenn gar nichts valide ist.

    Args:
        clip: Optional der MovieClip. Fällt zurück auf den aktiven Clip.
        object_name: Optional der Name des MovieTrackingObject für Object-Solve.

    Returns:
        float: gewichteter durchschnittlicher Error in Pixeln.
    """
    # 1) Clip ermitteln
    if clip is None:
        clip = getattr(bpy.context, "edit_movieclip", None) or getattr(
            bpy.context.scene, "movieclip", None
        )
    if clip is None:
        return 0.0  # Kein Clip im Kontext

    tracking = clip.tracking

    # 2) Relevante Tracks holen
    tracks = _get_tracks_for_solve(tracking, object_name)
    if tracks:
        avg_err = _compute_weighted_average_error(tracks)
        if avg_err > 0.0:
            return avg_err

    # 3) Fallback: Reconstruction-average_error (Object oder Camera)
    if object_name:
        mobj = tracking.objects.get(object_name)
        recon = getattr(mobj, "reconstruction", None) if mobj else None
        if recon and getattr(recon, "is_valid", False):
            err = getattr(recon, "average_error", None)
            return _safe_error_value(err)
    else:
        recon = getattr(tracking, "reconstruction", None)
        if recon and getattr(recon, "is_valid", False):
            err = getattr(recon, "average_error", None)
            return _safe_error_value(err)

    # 4) Letzter Fallback
    return 0.0


#
# --- Beispiele (nur bei direktem Ausführen) ---
#
if __name__ == "__main__":
    # Kamera-Solve:
    err_cam = get_average_error()
    print(f"[get_average_error] Camera Error (weighted): {err_cam}")

    # Object-Solve (Name aus dem Tracking-Panel, z.B. 'Object'):
    err_obj = get_average_error(object_name="Object")
    print(f"[get_average_error] Object Error (weighted): {err_obj}")
