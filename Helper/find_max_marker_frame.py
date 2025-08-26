from __future__ import annotations
"""
Helper: find_max_marker_frame (mit detailliertem Logging)
--------------------------------------------------------

- Schwelle: ``threshold = scene.marker_frame * 2``
- Scan-Bereich: ``scene.frame_start .. scene.frame_end`` (inklusiv)
- Rückgabe bei Treffer: {status: "FOUND", frame, count, threshold}
- Rückgabe ohne Treffer: {status: "NONE", threshold, observed_min, observed_min_frame}
- Konsistentes Log pro Frame: ``[find_max_marker_frame] frame=… count=… threshold=…``

Hinweis: Gemutete Tracks/Marker werden ignoriert, pro Track wird maximal 1 Marker
gezählt (früher Ausstieg im Marker-Loop).
"""

from typing import Optional, Dict, Any
import bpy

__all__ = ["run_find_max_marker_frame"]


# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------


def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Aktiven MovieClip bestimmen (bevorzugt CLIP_EDITOR, sonst erstes MovieClip)."""
    try:
        space = getattr(context, "space_data", None)
        if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
            return space.clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip) -> Optional[bpy.types.bpy_prop_collection]:
    """Bevorzuge Tracks des aktiven Tracking-Objekts; Fallback: Clip-Root-Tracks."""
    if not clip:
        return None
    try:
        obj = clip.tracking.objects.active
        if obj and getattr(obj, "tracks", None):
            return obj.tracks
    except Exception:
        pass
    try:
        return clip.tracking.tracks
    except Exception:
        return None


def _count_active_markers_at_frame(tracks, frame: int) -> int:
    """Zählt aktive Marker an *frame* über alle Tracks (max. 1 je Track)."""
    f = int(frame)
    count = 0
    for tr in tracks or []:
        try:
            if bool(getattr(tr, "mute", False)):
                continue
            for m in tr.markers:
                if int(getattr(m, "frame", -10 ** 9)) == f:
                    if not bool(getattr(m, "mute", False)):
                        count += 1
                    break  # pro Track nur einmal zählen
        except Exception:
            continue
    return count


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------


def run_find_max_marker_frame(
    context: bpy.types.Context,
    *,
    log_each_frame: bool = True,
    return_observed_min: bool = True,
) -> Dict[str, Any]:
    """Sucht den **ersten** Frame im Szenenbereich, dessen aktive Markerzahl
    unter ``threshold = scene.marker_frame * 2`` liegt.
    
    Zusätzlich werden (falls kein Treffer) das kleinste beobachtete ``count``
    sowie der zugehörige Frame zurückgegeben, um heuristische Entscheidungen
    außerhalb zu erleichtern.
    """
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    scene = context.scene
    try:
        marker_frame_val = int(getattr(scene, "marker_frame", scene.frame_current) or scene.frame_current)
    except Exception:
        marker_frame_val = int(getattr(scene, "frame_current", 0) or 0)
    threshold = int(marker_frame_val * 2)

    tracks = _get_tracks_collection(clip)
    if tracks is None:
        # Kein Tracking-Kontext vorhanden → keine Marker → keine Treffer
        out = {"status": "NONE", "threshold": threshold}
        if return_observed_min:
            out.update({"observed_min": 0, "observed_min_frame": int(getattr(scene, "frame_start", 1) or 1)})
        return out

    # Szenenbereich bestimmen (robust gegen vertauschte Grenzen)
    s_start = int(getattr(scene, "frame_start", 1) or 1)
    s_end = int(getattr(scene, "frame_end", s_start) or s_start)
    if s_end < s_start:
        s_start, s_end = s_end, s_start

    observed_min = None
    observed_min_frame = None

    for f in range(s_start, s_end + 1):
        c = _count_active_markers_at_frame(tracks, f)
        if log_each_frame:
            print(f"[find_max_marker_frame] frame={f} count={c} threshold={threshold}")

        # Minimum mitführen
        if observed_min is None or c < observed_min:
            observed_min = c
            observed_min_frame = f

        if c < threshold:
            return {
                "status": "FOUND",
                "frame": int(f),
                "count": int(c),
                "threshold": int(threshold),
            }

    # Kein Treffer → optional min zurückgeben
    out: Dict[str, Any] = {"status": "NONE", "threshold": int(threshold)}
    if return_observed_min:
        out.update({
            "observed_min": int(observed_min or 0),
            "observed_min_frame": int(observed_min_frame or s_start),
        })
    return out
