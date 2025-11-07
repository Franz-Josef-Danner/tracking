# Helper/filter_tracks.py
# ------------------------------------------------------------
# Führt den Blender-internen Filter zur Track-Bereinigung aus
# und löscht Tracks unterhalb einer per UI gesetzten Mindestlänge.
# ------------------------------------------------------------

import bpy
from typing import Optional


def _get_ui_min_frames(context: bpy.types.Context, fallback: int = 25) -> int:
    """
    Liest die Mindestanzahl an Frames pro Track aus der Scene-Property
    'kaiserlich_frames_per_track'. Fällt robust auf 'fallback' zurück.
    """
    try:
        scene = context.scene
        if scene is None:
            raise AttributeError("context.scene is None")

        value = getattr(scene, "kaiserlich_frames_per_track", None)
        if value is None:
            return int(fallback)

        # Defensive cast & Validierung
        ivalue = int(value)
        if ivalue < 0:
            return int(fallback)
        return ivalue
    except Exception as e:
        return int(fallback)


def filter_problematic_tracks(
    context: bpy.types.Context,
    threshold: float = 10.0,
    min_frames: Optional[int] = None,
) -> None:
    """
    1) Wendet den internen Bewegungs-Filter an (clip.filter_tracks).
    2) Führt ein Cleanup aus und löscht Tracks, die kürzer sind als
       die in der UI definierte Mindestlänge (Frames per Track).

    Args:
        context: Blender Context (erwartet aktiven Movie Clip im Clip Editor).
        threshold: Threshold für den internen Filter.
        protected_names: Optionale Menge an Track-Namen, die niemals gelöscht werden dürfen.
    """
    # Sicherstellen, dass wir im Movie Clip Editor sind
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        return

    clip = space_data.clip

    # --- 0) UI-Wert für min_frames auflösen (falls nicht manuell gesetzt)
    resolved_min_frames = _get_ui_min_frames(context, fallback=25) if min_frames is None else int(min_frames)

    # --- 0.5) Geschützte Namen aus Szene (optional übergeben) ---
    protected_names = getattr(context.scene, "kaiserlich_protected_tracks", set()) or set()
    if not isinstance(protected_names, set):
        protected_names = set(protected_names)

    if protected_names:
        for tr in clip.tracking.tracks:
            if tr.name in protected_names:
                tr.select = False
                tr.lock = True

    # --- 1) Interner Filter (Bewegungsanalyse)
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")
        return

    # --- 2) Cleanup für kurze Tracks
    try:
        tracking_settings = clip.tracking.settings
        tracking_settings.clean_action = 'DELETE_TRACK'  # Alternativen: 'SELECT', 'DELETE_SEGMENTS'
        tracking_settings.clean_error = 0.0              # nur Frames-Kriterium nutzen
        tracking_settings.clean_frames = resolved_min_frames

        bpy.ops.clip.clean_tracks()

        print(f"[Kaiserlich Tracker][Filter] Cleanup ✓ – Tracks mit < {resolved_min_frames} Frames gelöscht.")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Cleanup: {e}")

    # --- 3) Schutz wieder aufheben ---
    if protected_names:
        for tr in clip.tracking.tracks:
            if tr.name in protected_names:
                tr.lock = False
