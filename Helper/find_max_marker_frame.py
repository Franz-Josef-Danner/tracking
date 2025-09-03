from __future__ import annotations

from typing import Optional, Dict, Any, List
import bpy

__all__ = ["run_find_max_marker_frame"]

# Scene-Flag, das vom Coordinator gesetzt wird, wenn der Spike-Cycle erschöpft ist
SPIKE_FLAG_SCENE_KEY = "tco_spike_cycle_finished"


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


def _build_frame_counts(tracks, start_frame: int, end_frame: int) -> List[int]:
    """Erzeugt ein Histogramm der Marker-Anzahl je Frame im [start..end]-Intervall.

    - Ignoriert gemutete Tracks/Marker
    - Zählt je Track pro Frame höchstens 1 Marker
    - Robust gegen unsortierte Markerlisten
    """
    s = int(start_frame)
    e = int(end_frame)
    n = e - s + 1
    if n <= 0:
        return []

    counts = [0] * n

    for tr in list(tracks) if tracks is not None else []:
        try:
            if bool(getattr(tr, "mute", False)):
                continue
            last_frame = None  # verhindert Doppelzählungen im selben Track/Frame
            for m in getattr(tr, "markers", []):
                try:
                    f = int(getattr(m, "frame", -10 ** 9))
                except Exception:
                    continue
                if f < s or f > e:
                    continue
                if bool(getattr(m, "mute", False)):
                    continue
                if last_frame == f:
                    # pro Track & Frame nur ein Marker
                    continue
                counts[f - s] += 1
                last_frame = f
        except Exception:
            # Defekten Track ignorieren
            continue

    return counts


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
    unter der Schwelle aus der **marker_basis**-Logik liegt.

    Schwellenwert-Quelle (Priorität):
      1) scene["marker_adapt"], wenn scene["prefer_marker_adapt"] == True
      2) scene["marker_basis"]
      3) Fallback: 20
    Effektiver Vergleich: count <= (basis - 1)

    Zusätzlich werden (falls kein Treffer) das kleinste beobachtete ``count``
    sowie der zugehörige Frame zurückgegeben, um heuristische Entscheidungen
    außerhalb zu erleichtern.
    """
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    scene = context.scene
    # --- Schwellenwert wie in run_find_low_marker_frame: basis bzw. adapt, Fallback 20 ---
    try:
        prefer_adapt = bool(scene.get("prefer_marker_adapt", False))
        if prefer_adapt and "marker_adapt" in scene:
            _basis = int(scene["marker_adapt"])
        elif "marker_basis" in scene:
            _basis = int(scene["marker_basis"])
        else:
            _basis = 20
    except Exception:
        _basis = 20
    # Effektiv: count <= (basis - 1)
    threshold = max(0, int(_basis) - 1)

    tracks = _get_tracks_collection(clip)
    if tracks is None:
        # Kein Tracking-Kontext vorhanden → keine Marker → keine Treffer
        out = {"status": "NONE", "threshold": threshold, "basis": int(_basis)}
        if return_observed_min:
            out.update({"observed_min": 0, "observed_min_frame": int(getattr(scene, "frame_start", 1) or 1)})
        return out

    # Szenenbereich bestimmen (robust gegen vertauschte Grenzen)
    s_start = int(getattr(scene, "frame_start", 1) or 1)
    s_end = int(getattr(scene, "frame_end", s_start) or s_start)
    if s_end < s_start:
        s_start, s_end = s_end, s_start

    # Einmalig zählen → schnell
    counts = _build_frame_counts(tracks, s_start, s_end)

    observed_min = None
    observed_min_frame = None

    # Linearer Sweep über die gezählten Werte
    for idx, c in enumerate(counts):
        f = s_start + idx
        if log_each_frame:
            pass
        if observed_min is None or c < observed_min:
            observed_min = c
            observed_min_frame = f

        if c <= threshold:
            return {
                "status": "FOUND",
                "frame": int(f),
                "count": int(c),
                "threshold": int(threshold),
                "basis": int(_basis),
            }

    # Kein Treffer → optional min zurückgeben
    out: Dict[str, Any] = {"status": "NONE", "threshold": int(threshold), "basis": int(_basis)}
    if return_observed_min:
        out.update({
            "observed_min": int(observed_min or 0),
            "observed_min_frame": int(observed_min_frame or s_start),
        })
    # Terminal-Log, falls Spike-Zyklus als ausgereizt markiert wurde – nur einmal loggen
    try:
        scn = getattr(context, 'scene', None)
        if scn is not None and bool(scn.get(SPIKE_FLAG_SCENE_KEY, False)):
            if not bool(scn.get("tco_spike_finish_logged", False)):
                print('finish')
                scn["tco_spike_finish_logged"] = True
    except Exception:
        pass
    return out
