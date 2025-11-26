# Helper/solve_validation.py
from __future__ import annotations
import bpy
from typing import Optional


# ============================================================
# Solve-Validation Helper
# Prüft, ob ausreichend stabile Tracks zur 3D-Rekonstruktion vorliegen
# ============================================================

def has_solve_basis(context: bpy.types.Context,
                    min_tracks: int = 6,
                    min_span: int = 8) -> bool:
    """
    Prüft, ob ein Solve überhaupt Sinn macht:
      • genügend Tracks
      • Track-Spanne (Frames) groß genug für Parallax/3D-Basis
    """
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) or getattr(context.scene.tracking, "active", None)
    if not clip or not getattr(clip, "tracking", None):
        return False

    valid = 0
    for tr in clip.tracking.tracks:
        if getattr(tr, "mute", False):     # ignoriert deaktivierte Tracks
            continue

        # Alle gültigen Marker dieses Tracks
        frames = [m.frame for m in tr.markers if not getattr(m, "mute", False)]
        if not frames:
            continue

        # Span berechnen
        span = max(frames) - min(frames)
        if span >= min_span:
            valid += 1

        # Früh-Abbruch wenn genug gefunden
        if valid >= min_tracks:
            return True

    return False


def get_solve_basis_stats(context: bpy.types.Context) -> tuple[int, list[int]]:
    """
    Liefert Diagnose-Infos:
      count_valid_tracks, frame_spans
    Nutzbar für Logging vor Solve.
    """
    spans = []
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) or getattr(context.scene.tracking, "active", None)
    if not clip or not getattr(clip, "tracking", None):
        return 0, []

    for tr in clip.tracking.tracks:
        if getattr(tr, "mute", False):
            continue

        frames = [m.frame for m in tr.markers if not getattr(m, "mute", False)]
        if not frames:
            continue

        spans.append(max(frames) - min(frames))

    valid = sum(1 for s in spans if s >= 8)
    return valid, spans
