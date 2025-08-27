from __future__ import annotations

from typing import Optional, Dict, Any, List
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
                    f = int(getattr(m, "frame", -10**9))
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

def _resolve_threshold_from_scene(scene: bpy.types.Scene) -> Optional[int]:
    """Liest optionale Szene-Hints aus (kompatibel zu Legacy-Aufrufern)."""
    try:
        if hasattr(scene, "find_max_start_threshold"):
            val = getattr(scene, "find_max_start_threshold")
            if val is not None:
                return int(val)
    except Exception:
        pass
    return None


def _resolve_reuse_last_from_scene(scene: bpy.types.Scene) -> Optional[bool]:
    try:
        if hasattr(scene, "find_max_reuse_last"):
            return bool(getattr(scene, "find_max_reuse_last"))
    except Exception:
        pass
    return None


def _get_default_legacy_threshold(scene: bpy.types.Scene) -> int:
    """Legacy-Fallback: threshold aus marker_frame*1.1 ableiten."""
    try:
        marker_frame_val = int(getattr(scene, "marker_frame", scene.frame_current) or scene.frame_current)
    except Exception:
        marker_frame_val = int(getattr(scene, "frame_current", 0) or 0)
    return int(marker_frame_val * 1.1)


def run_find_max_marker_frame(
    context: bpy.types.Context,
    *,
    # NEU: immer bei fixem Wert starten können (z. B. 50)
    start_threshold: Optional[float] = None,
    # NEU: ob ein "zuletzt verwendeter" Wert wiederverwendet werden darf
    reuse_last: bool = True,
    log_each_frame: bool = True,
    return_observed_min: bool = True,
) -> Dict[str, Any]:
    """Sucht den **ersten** Frame im Szenenbereich, dessen aktive Markerzahl
    unter ``threshold`` liegt.

    Threshold-Ermittlung (Priorität absteigend):
      1) Expliziter Parameter ``start_threshold`` (z. B. 50)
      2) Szene-Hint ``scene.find_max_start_threshold`` (Legacy-Integration)
      3) (optional) Wiederverwendung ``scene.find_max_last_threshold`` wenn ``reuse_last=True``
      4) Legacy-Fallback: ``int(scene.marker_frame * 1.1)``
    """
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    scene = context.scene

    # --- Threshold bestimmen nach Priorität ---
    threshold: Optional[int] = None

    # 1) Expliziter Funktions-Parameter
    if start_threshold is not None:
        try:
            threshold = int(start_threshold)
        except Exception:
            threshold = None

    # 2) Szene-Hint (nur, wenn noch nicht gesetzt)
    if threshold is None:
        scene_hint = _resolve_threshold_from_scene(scene)
        if scene_hint is not None:
            threshold = int(scene_hint)

    # 3) Reuse-Last (nur wenn erlaubt UND kein expliziter Start gesetzt)
    if threshold is None:
        reuse_flag = reuse_last
        scene_reuse_opt = _resolve_reuse_last_from_scene(scene)
        if scene_reuse_opt is not None:
            reuse_flag = bool(scene_reuse_opt)
        if reuse_flag:
            try:
                last_thr = getattr(scene, "find_max_last_threshold", None)
                if last_thr is not None:
                    threshold = int(last_thr)
            except Exception:
                pass

    # 4) Legacy-Fallback
    if threshold is None:
        threshold = _get_default_legacy_threshold(scene)

    # Sicherheitsklemme
    threshold = max(int(threshold), 0)

    tracks = _get_tracks_collection(clip)
    if tracks is None:
        out = {"status": "NONE", "threshold": int(threshold)}
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
            print(f"[find_max_marker_frame] frame={f} count={c} threshold={threshold}")

        if observed_min is None or c < observed_min:
            observed_min = c
            observed_min_frame = f

        if c <= threshold:
            # den tatsächlich verwendeten Threshold im Scene-State persistieren (nur Info)
            try:
                setattr(scene, "find_max_last_threshold", int(threshold))
            except Exception:
                pass
            return {
                "status": "FOUND",
                "frame": int(f),
                "count": int(c),
                "threshold": int(threshold),
            }

    # Kein Treffer → optional min zurückgeben
    try:
        setattr(scene, "find_max_last_threshold", int(threshold))
    except Exception:
        pass

    out: Dict[str, Any] = {"status": "NONE", "threshold": int(threshold)}
    if return_observed_min:
        out.update({
            "observed_min": int(observed_min or 0),
            "observed_min_frame": int(observed_min_frame or s_start),
        })
    return out