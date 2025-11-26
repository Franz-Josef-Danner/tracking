from __future__ import annotations
import bpy
from typing import Iterable, Callable

def get_total_track_length(
    context: bpy.types.Context,
    start_frame: int = 1,
    *,
    include_names: Iterable[str] | None = None,
    logger: Callable[[str], None] | None = None,  # nur für Fehlerfälle
) -> int:
    """
    Zählt nur Frames mit *aktiven* Markern pro Track ab `start_frame`.
    Aktiv bedeutet:
      - marker.mute == False
      - pattern_corners enthält mindestens eine Ecke ≠ (0.0, 0.0)
    """

    # Helper für optionales, minimales Logging (nur Fehler)
    def _log(msg: str) -> None:
        if logger is not None:
            logger(msg)

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        _log("Kein aktiver Clip im Kontext. Rückgabe: 0.")
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        _log("Kein Tracking-Container gefunden. Rückgabe: 0.")
        return 0

    tracks = (
        tracking.objects.active.tracks
        if getattr(tracking.objects, "active", None)
        else tracking.tracks
    )

    total_length = 0

    for tr in tracks:
        if include_names is not None and tr.name not in include_names:
            continue

        # aktive Marker ab start_frame
        active_frames = (
            mk.frame
            for mk in tr.markers
            if mk.frame >= start_frame
            and not getattr(mk, "mute", False)
            and any(corner != (0.0, 0.0) for corner in getattr(mk, "pattern_corners", []))
        )

        # statt Liste: direkt zählen (O(n), ohne Speicher)
        count_active = 0
        for _ in active_frames:
            count_active += 1

        total_length += count_active

    return total_length
