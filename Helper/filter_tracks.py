# Helper/filter_tracks.py
# ------------------------------------------------------------
# Führt den Blender-internen Filter zur Track-Bereinigung aus
# und löscht anschließend Tracks mit zu kurzer Länge.
# ------------------------------------------------------------

import bpy


def filter_problematic_tracks(context: bpy.types.Context, threshold: float = 10.0, min_frames: int = 25) -> None:
    """
    Wendet den internen Blender-Filter auf Tracking-Daten an, um
    fehlerhafte Tracks zu bereinigen und anschließend alle Tracks
    zu löschen, die kürzer als 'min_frames' sind.

    Args:
        context (bpy.types.Context): Der aktuelle Blender-Kontext.
        threshold (float): Schwellenwert für den internen Track-Filter.
        min_frames (int): Mindestanzahl an Frames, die ein Track haben muss.
                          Tracks mit weniger Frames werden gelöscht.
    """

    # Sicherstellen, dass wir im Movie Clip Editor sind
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        print("[Kaiserlich Tracker][Filter] ❌ Kein aktiver Movie Clip gefunden.")
        return

    clip = space_data.clip
    print(f"[Kaiserlich Tracker][Filter] Aktiver Clip: {clip.name}")

    # ------------------------------------------------------------
    # 1. Interner Filter (Bewegungsanalyse)
    # ------------------------------------------------------------
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter erfolgreich angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")
        return

    # ------------------------------------------------------------
    # 2. Cleanup für kurze oder fehlerhafte Tracks
    # ------------------------------------------------------------
    try:
        tracking_settings = clip.tracking.settings
        tracking_settings.clean_action = 'DELETE_TRACK'
        tracking_settings.clean_error = 0.0
        tracking_settings.clean_frames = min_frames

        bpy.ops.clip.clean_tracks()

        print(f"[Kaiserlich Tracker][Filter] Cleanup ausgeführt – "
              f"Tracks mit weniger als {min_frames} Frames wurden gelöscht.")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Cleanup: {e}")