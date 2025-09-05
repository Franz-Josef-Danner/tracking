# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/find_max_error_frame.py

Sucht den Frame mit dem höchsten aggregierten Fehler-Score.
Heuristik: Pro Frame wird der Mittelwert der `track.average_error` aller Tracks
gebildet, die an diesem Frame eine Markierung besitzen (optional gefiltert).

Public API:
    run_find_max_error_frame(context,
                             include_muted=False,
                             min_tracks_per_frame=10,
                             frame_min=None,
                             frame_max=None,
                             return_top_k=5,
                             verbose=True) -> dict

Rückgabe (Beispiel):
    {
        'status': 'FOUND',
        'frame': 153,
        'score': 12.3478,      # durchschnittlicher Score am "schlechtesten" Frame
        'count': 87,           # Anzahl Tracks, die an diesem Frame beitragen
        'top': [
            {'frame': 153, 'score': 12.3478, 'count': 87},
            {'frame': 221, 'score': 11.9012, 'count': 74},
            ...
        ],
        'min_tracks_per_frame': 10
    }

Hinweis:
- Wir verwenden `track.average_error` als Proxy pro Track und mappen ihn auf die
  Frames, an denen der Track Marker hat. Das ist extrem schnell und in der Praxis
  sehr nah an "Frame mit höchster Problem-Dichte".
- Wenn streng per-Frame-Reprojektion gewünscht ist, kann später eine
  Reprojektions-Variante ergänzt werden (3D-„bundle“ + per-Frame Kamera).
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional
import bpy


__all__ = ("run_find_max_error_frame",)


def _get_active_clip(context: bpy.types.Context):
    # Bevorzugt den aktiven CLIP_EDITOR; fällt andernfalls auf edit_movieclip zurück.
    try:
        sd = getattr(context, "space_data", None)
        if sd and getattr(sd, "type", None) == "CLIP_EDITOR" and getattr(sd, "clip", None):
            return sd.clip
    except Exception:
        pass
    try:
        clip = getattr(context, "edit_movieclip", None)
        if clip:
            return clip
    except Exception:
        pass
    # Fallback: erster Clip in der Datei (falls vorhanden)
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def run_find_max_error_frame(
    context: bpy.types.Context,
    *,
    include_muted: bool = False,
    min_tracks_per_frame: int = 10,
    frame_min: Optional[int] = None,
    frame_max: Optional[int] = None,
    return_top_k: int = 5,
    verbose: bool = True,
) -> Dict[str, Any]:
    scn = context.scene
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "NO_CLIP", "reason": "Kein aktiver MovieClip gefunden."}

    tracks = getattr(clip.tracking, "tracks", None)
    if not tracks or len(tracks) == 0:
        return {"status": "NO_TRACKS", "reason": "Keine Tracks im Clip vorhanden."}

    # Standardmäßig nur innerhalb des Szenenfensters auswerten
    if frame_min is None:
        frame_min = int(scn.frame_start)
    if frame_max is None:
        frame_max = int(scn.frame_end)

    frame_errors: Dict[int, List[float]] = defaultdict(list)

    # Mappe avg_error eines Tracks auf alle Frames, an denen der Track Marker hat
    for tr in tracks:
        try:
            if (not include_muted) and getattr(tr, "mute", False):
                continue
            avg_err = float(getattr(tr, "average_error", 0.0) or 0.0)
        except Exception:
            continue

        # Skip vollständig „perfekte“/nichtssagende Tracks
        if avg_err <= 0.0:
            continue

        try:
            markers = tr.markers
        except Exception:
            continue

        for m in markers:
            try:
                f = int(getattr(m, "frame", None))
            except Exception:
                continue
            if f is None:
                continue
            if frame_min is not None and f < int(frame_min):
                continue
            if frame_max is not None and f > int(frame_max):
                continue
            frame_errors[f].append(avg_err)

    # Aggregiere per Frame
    stats: List[Tuple[int, float, int]] = []
    for f, errs in frame_errors.items():
        if not errs:
            continue
        count = len(errs)
        # Primärfilter auf Mindestabdeckung
        if count < int(min_tracks_per_frame):
            continue
        score = sum(errs) / count
        stats.append((f, score, count))

    # Fallback, falls der Mindest-Coverage-Filter zu strikt war
    if not stats:
        for f, errs in frame_errors.items():
            if not errs:
                continue
            count = len(errs)
            score = sum(errs) / count
            stats.append((f, score, count))

    if not stats:
        return {"status": "NO_MARKERS", "reason": "Keine verwertbaren Marker zur Fehleraggregation gefunden."}

    # Sortiere absteigend nach Score
    stats.sort(key=lambda x: x[1], reverse=True)
    top = stats[: max(1, int(return_top_k))]
    best_frame, best_score, best_count = top[0]

    # Szene auf den „schlechtesten“ Frame setzen (bequemer Default), aber clamped
    try:
        lo = int(frame_min) if frame_min is not None else int(scn.frame_start)
        hi = int(frame_max) if frame_max is not None else int(scn.frame_end)
        target = max(lo, min(hi, int(best_frame)))
        scn.frame_set(target)
    except Exception:
        pass

    result = {
        "status": "FOUND",
        "frame": int(best_frame),
        "score": float(best_score),
        "count": int(best_count),
        "top": [{"frame": int(f), "score": float(s), "count": int(c)} for (f, s, c) in top],
        "min_tracks_per_frame": int(min_tracks_per_frame),
    }

    if verbose:
        try:
            print(f"[FindMaxErrorFrame] clip='{clip.name}' best_frame={best_frame} score={best_score:.4f} count={best_count} (min={min_tracks_per_frame})")
            print(f"[FindMaxErrorFrame] top={result['top']}")
        except Exception:
            pass

    return result
