# Helper/projection_cleanup_builtin.py
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Iterable, List
import bpy
import math
import time

__all__ = ("run_projection_cleanup_builtin",)

_STORE_TRACKS_KEY = "tco_proj_spike_tracks"  # Übergabe an projektion_spike_filter_cycle
_SCENE_ERROR_KEY  = "error_track"            # Basiswert aus Scene

# ---------------------------------------------------------------------
# Kontext
# ---------------------------------------------------------------------
def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return next(iter(bpy.data.movieclips), None)
    except Exception:
        return None

def _iter_tracks(clip: Optional[bpy.types.MovieClip]) -> Iterable[bpy.types.MovieTrackingTrack]:
    if not clip:
        return []
    try:
        for obj in clip.tracking.objects:
            for t in obj.tracks:
                yield t
    except Exception:
        return []

# ---------------------------------------------------------------------
# Kernlogik
# ---------------------------------------------------------------------
def _scene_error_basis(scene: bpy.types.Scene | None) -> float | None:
    """Liest scene.error_track defensiv; None wenn nicht gesetzt/ungültig."""
    if not scene:
        return None
    try:
        v = scene.get(_SCENE_ERROR_KEY, None)
        return float(v) if v is not None else None
    except Exception:
        return None

def _compute_track_errors(clip: bpy.types.MovieClip) -> list[tuple[str, float]]:
    """
    Liefert (track_name, per-Track-Error). Primär 'average_error',
    Fallbacks: 'reprojection_error', 'error'. 0.0 ist zulässig.
    """
    out: list[tuple[str, float]] = []
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    candidates = ("average_error", "reprojection_error", "error")
    for obj in clip.tracking.objects:
        for t in obj.tracks:
            val = None
            for attr in candidates:
                if hasattr(t, attr):
                    try:
                        val = getattr(t, attr)
                        break
                    except Exception:
                        val = None
            if val is None:
                continue
            try:
                err = float(val)
            except Exception:
                continue
            # nur NaN/Inf verwerfen, 0.0 zulassen
            if math.isfinite(err) and err >= 0.0:
                out.append((t.name, err))
    return out

# ---------------------------------------------------------------------
# Öffentliche API – selektiert nur, speichert Track-Namen
# ---------------------------------------------------------------------
def run_projection_cleanup_builtin(
    context: bpy.types.Context,
    *,
    wait_for_error: bool = False,
    timeout_s: float = 0.0,
) -> Dict[str, Any]:
    """
    Selektiert die fehlerstärksten Tracks und persistiert deren Namen in
    scene['tco_proj_spike_tracks'] gemäß Formel:
        error_basis = scene.error_track (Fallback 1.0)
        error_T     = max(average_error)
        n_select    = ceil(error_T / error_basis)

    Rückgabe: {status, n_total, n_selected, error_basis, error_T, selected_names, store_key}
    """
    clip = _active_clip(context)
    if not clip:
        return {"status": "SKIPPED", "reason": "no_active_clip"}

    errs = _compute_track_errors(clip)
    if not errs:
        # Tieferer Hinweis, wie viele Tracks es überhaupt gibt
        return {
            "status": "SKIPPED",
            "reason": "no_track_errors",
            "n_total": sum(1 for _ in _iter_tracks(clip)),
        }

    scene = getattr(context, "scene", None)
    error_basis = _scene_error_basis(scene)
    if not (isinstance(error_basis, (int, float)) and error_basis > 0.0):
        error_basis = 1.0  # defensiver Default

    error_T = max(e for _, e in errs)
    n_select = min(len(errs), max(1, int(math.ceil(error_T / error_basis))))

    errs.sort(key=lambda kv: kv[1], reverse=True)
    selected_names = [name for name, _ in errs[:n_select]]

    # UI-Selektion (optional hilfreich fürs Debugging)
    try:
        names = set(selected_names)
        for t in _iter_tracks(clip):
            t.select = t.name in names
    except Exception:
        pass

    # Übergabe an den Spike-Pass
    try:
        scene[_STORE_TRACKS_KEY] = selected_names
    except Exception:
        pass

    return {
        "status": "OK",
        "n_total": len(errs),
        "n_selected": len(selected_names),
        "error_basis": float(error_basis),
        "error_T": float(error_T),
        "selected_names": selected_names,
        "store_key": _STORE_TRACKS_KEY,
    }

