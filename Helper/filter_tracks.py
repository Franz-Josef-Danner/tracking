# Helper/filter_tracks.py
# ------------------------------------------------------------
# Führt den Blender-internen Filter zur Track-Bereinigung aus.
# ------------------------------------------------------------

import bpy


def filter_problematic_tracks(context: bpy.types.Context, threshold: float = 10.0) -> None:
    """
    Wendet den internen Blender-Filter auf Tracking-Daten an, um
    fehlerhafte Tracks mit unnatürlichen Bewegungs-Spikes zu entfernen.

    Args:
        context (bpy.types.Context): Der aktuelle Blender-Kontext.
        threshold (float): Der Schwellenwert für den internen Filter.
                           Je höher der Wert, desto toleranter ist der Filter.
                           Standardwert: 10.0
    """

    # Sicherstellen, dass wir im Movie Clip Editor sind
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        print("[Kaiserlich Tracker][Filter] ❌ Kein aktiver Movie Clip gefunden.")
        return

    clip = space_data.clip
    print(f"[Kaiserlich Tracker][Filter] Aktiver Clip: {clip.name}")

    # Operator aufrufen
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter erfolgreich angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")