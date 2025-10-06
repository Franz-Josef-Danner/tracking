from typing import Final
import bpy  # type: ignore

# Öffentlich genutzter Default (laut Anforderung: int in [1])
default_frames_limit: Final[int] = 1

def resolve_frames_limit(context, fallback: int | None = None) -> int:
    """Ermittelt das effektive Frames-Limit.

    Aktuell nur Rückgabe der Konstante, aber als Funktion gekapselt um später
    auf Scene-/Addon-Properties erweitern zu können.
    """
    if fallback is not None and fallback > 0:
        return fallback
    return default_frames_limit


def set_one_frame_limit(clip, *, only_selected: bool = True) -> int:
    """Setzt das Frame-Limit auf 1.

    Anpassungen:
      - Tracking Settings: default_frames_limit / default_frame_limit
      - Tracks: frames_limit / frame_limit

    Args:
        clip: Aktiver MovieClip
        only_selected: Wenn True, nur selektierte Tracks umstellen (empfohlen)

    Returns:
        int: Anzahl der angepassten Entities (Settings + Tracks)
    """
    if not clip:
        return 0
    changed = 0
    tracking = getattr(clip, 'tracking', None)
    if not tracking:
        return 0
    settings = getattr(tracking, 'settings', None)
    if settings:
        for attr in ("default_frames_limit", "default_frame_limit"):
            if hasattr(settings, attr):
                try:
                    setattr(settings, attr, 1)
                    print(f"[Kaiserlich Tracker] {attr} -> 1 (Settings)")
                    changed += 1
                except Exception:
                    pass
    tracks = getattr(tracking, 'tracks', [])
    for trk in tracks:
        if only_selected and not getattr(trk, 'select', False):
            continue
        for attr in ("frames_limit", "frame_limit"):
            if hasattr(trk, attr):
                try:
                    setattr(trk, attr, 1)
                    print(f"[Kaiserlich Tracker] Track {getattr(trk,'name','?')}: {attr} -> 1")
                    changed += 1
                except Exception:
                    pass
    return changed

__all__ = [
    'default_frames_limit',
    'resolve_frames_limit',
    'set_one_frame_limit',
]
