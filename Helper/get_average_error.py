# Helper/get_average_error.py
import bpy
from math import isnan


def _safe_error_value(err) -> float:
    """Konvertiert einen Error-Wert robust nach float.
    Fällt auf 0.0 zurück, wenn der Wert nicht existiert oder unbrauchbar ist.
    """
    if err is None:
        return 0.0
    try:
        value = float(err)
    except (TypeError, ValueError):
        return 0.0

    if isnan(value):
        return 0.0

    return value


def get_average_error(clip: bpy.types.MovieClip | None = None,
                      object_name: str | None = None) -> float:
    """
    Liefert den durchschnittlichen Solve-Fehler in Pixeln (average_error)
    aus Blenders Tracking-Rekonstruktion.

    Priorität:
    1) Wenn object_name gesetzt: average_error des Object-Solves
    2) Sonst: average_error des Kamera-Solves (global)

    Args:
        clip: Optional der MovieClip. Fällt zurück auf den aktiven Clip.
        object_name: Optional der Name des MovieTrackingObject für Object-Solve.

    Returns:
        float: average_error; 0.0 als Fallback, wenn nichts valide ist
               oder kein gültiger Error-Wert existiert.
    """
    # 1) Clip ermitteln
    if clip is None:
        clip = getattr(bpy.context, "edit_movieclip", None) or getattr(bpy.context.scene, "movieclip", None)
    if clip is None:
        return 0.0  # Kein Clip im Kontext

    tracking = clip.tracking

    # 2) Object-Solve priorisieren, wenn angefordert
    if object_name:
        mobj = tracking.objects.get(object_name)
        recon = getattr(mobj, "reconstruction", None) if mobj else None
        if recon and getattr(recon, "is_valid", False):
            # Absicherung, falls average_error nicht existiert oder None/NaN ist
            err = getattr(recon, "average_error", None)
            return _safe_error_value(err)
        else:
            return 0.0  # Objekt existiert nicht oder ist nicht solved

    # 3) Kamera-Solve (global)
    recon = getattr(tracking, "reconstruction", None)
    if recon and getattr(recon, "is_valid", False):
        # Absicherung, falls average_error nicht existiert oder None/NaN ist
        err = getattr(recon, "average_error", None)
        return _safe_error_value(err)

    # 4) Fallback
    return 0.0  # Nichts valide oder kein brauchbarer Error-Wert


#
# --- Beispiele (nur bei direktem Ausführen) ---
# Achtung: Dieser Block läuft NICHT beim Import im Blender-Add-on und ist damit import-sicher.
#
if __name__ == "__main__":
    # Kamera-Solve:
    err_cam = get_average_error()
    print(f"[get_average_error] Camera Error: {err_cam}")

    # Object-Solve (Name aus dem Tracking-Panel, z.B. 'Object'):
    err_obj = get_average_error(object_name="Object")
    print(f"[get_average_error] Object Error: {err_obj}")
