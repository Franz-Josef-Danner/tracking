# Helper/track_quality_metrics.py
import bpy

def compute_track_quality_metrics(context: bpy.types.Context) -> dict:
    """
    Berechnet Track-Qualität basierend auf Blender-Operatoren:
      - alle_tracks = bpy.ops.clip.select_all(action='TOGGLE')
      - unter_25 = bpy.ops.clip.clean_tracks(frames=25, error=0.0, action='SELECT')
      - spike_tracks = bpy.ops.clip.filter_tracks(track_threshold=5.0)
      - prozent = (100 / anzahl_alle_tracks) * saubere_tracks
    """

    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip if context.space_data and context.space_data.type == "CLIP_EDITOR" else None
    )
    if clip is None:
        return {
            "alle_tracks": [],
            "anzahl_alle_tracks": 0,
            "unter_25": [],
            "anzahl_unter_25": 0,
            "anzahl_lange_tracks": 0,
            "spike_tracks": [],
            "anzahl_spike_tracks": 0,
            "saubere_tracks": 0,
            "prozent": 0.0,
        }

    # --- Alle Tracks zählen ---
    alle_tracks = list(clip.tracking.tracks)
    anzahl_alle_tracks = len(alle_tracks)

    # --- Unter-25-Frame-Tracks (bpy Operator) ---
    try:
        bpy.ops.clip.clean_tracks(frames=25, error=0.0, action='SELECT')
        unter_25 = [t for t in clip.tracking.tracks if t.select]
        anzahl_unter_25 = len(unter_25)
    except Exception:
        unter_25 = []
        anzahl_unter_25 = 0

    # --- Lange Tracks ---
    anzahl_lange_tracks = max(0, anzahl_alle_tracks - anzahl_unter_25)

    # --- Spike-Detection (bpy Operator) ---
    try:
        bpy.ops.clip.filter_tracks(track_threshold=5.0)
        spike_tracks = [t for t in clip.tracking.tracks if t.select]
        anzahl_spike_tracks = len(spike_tracks)
    except Exception:
        spike_tracks = []
        anzahl_spike_tracks = 0

    # --- Saubere Tracks ---
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)

    # --- Prozentberechnung ---
    if anzahl_alle_tracks < 1:
        prozent = 0.0
    else:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

    return {
        "alle_tracks": alle_tracks,
        "anzahl_alle_tracks": anzahl_alle_tracks,
        "unter_25": unter_25,
        "anzahl_unter_25": anzahl_unter_25,
        "anzahl_lange_tracks": anzahl_lange_tracks,
        "spike_tracks": spike_tracks,
        "anzahl_spike_tracks": anzahl_spike_tracks,
        "saubere_tracks": saubere_tracks,
        "prozent": prozent,
    }
