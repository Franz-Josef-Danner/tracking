import bpy
from typing import Optional


def detect_features(context, *, placement='FRAME', margin: int = 16, threshold: float = 0.5, min_distance: int = 120) -> Optional[int]:
    """Wrap für bpy.ops.clip.detect_features mit Logging und Fehlerabfang.

    Parameter entsprechen der Blender-API:
      placement: 'FRAME' | 'INSIDE_GPENCIL' | 'OUTSIDE_GPENCIL'
      margin: nur Features weiter als margin Pixel vom Rand
      threshold: Qualitäts-Schwelle
      min_distance: Mindestabstand zwischen zwei Features

    Rückgabe: Anzahl erzeugter neuer Tracks (falls bestimmbar), sonst None.
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        print("[Kaiserlich Tracker] detect: Kein Clip aktiv.")
        return None

    # Vorherige Anzahl merken, um zu schätzen wie viele neu sind
    prev_count = len(clip.tracking.tracks)
    try:
        bpy.ops.clip.detect_features(placement=placement, margin=margin, threshold=threshold, min_distance=min_distance)
    except Exception as e:  # noqa
        print(f"[Kaiserlich Tracker] detect: Fehler beim Aufruf detect_features: {e}")
        return None

    new_count = len(clip.tracking.tracks)
    created = new_count - prev_count if new_count >= prev_count else None
    print(f"[Kaiserlich Tracker] detect: detect_features ausgeführt (placement={placement}, margin={margin}, threshold={threshold}, min_distance={min_distance})")
    if created is not None:
        print(f"[Kaiserlich Tracker] detect: ~{created} neue Tracks angelegt.")
    return created
