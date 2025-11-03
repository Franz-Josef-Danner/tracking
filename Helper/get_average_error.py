# Helper/get_average_error.py
import bpy

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
        float: average_error; 0.0 als Fallback wenn nichts valide ist.
    """
    # 1) Clip ermitteln
    if clip is None:
        clip = getattr(bpy.context, "edit_movieclip", None) or bpy.context.scene.movieclip
    if clip is None:
        return 0.0  # kein Clip im Kontext

    tracking = clip.tracking

    # 2) Object-Solve priorisieren, wenn angefordert
    if object_name:
        mobj = tracking.objects.get(object_name)
        if mobj and mobj.reconstruction and mobj.reconstruction.is_valid:
            return float(mobj.reconstruction.average_error)
        else:
            return 0.0  # angefragtes Objekt existiert nicht oder ist nicht solved

    # 3) Kamera-Solve (global)
    recon = getattr(tracking, "reconstruction", None)
    if recon and recon.is_valid:
        return float(recon.average_error)

    return 0.0  # nichts valide

#
# --- Beispiele (nur bei direktem Ausführen) ---
# Achtung: Dieser Block läuft NICHT beim Import im Blender-Add-on und ist damit import-sicher.
#
if __name__ == "__main__":
    # Kamera-Solve:
    err_cam = get_average_error()
    print("Camera average error:", err_cam)

    # Object-Solve (Name aus dem Tracking-Panel, z.B. 'Object'):
    err_obj = get_average_error(object_name="Object")
    print("Object average error:", err_obj)
