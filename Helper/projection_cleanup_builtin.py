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
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
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
def _compute_track_errors(clip: bpy.types.MovieClip) -> list[tuple[str, float]]:
    """
    Liefert (track_name, reprojection_error) für alle Tracks, die einen numerischen Error tragen.
    Kein has_bundle-Gate mehr; 0.0 ist zulässig.
    """
    out: list[tuple[str, float]] = []
    if not clip:
        return out

    # Sicherstellen, dass die UI/Depsgraph frisch ist (manche Werte materialisieren erst nach Update)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    for obj in clip.tracking.objects:
        for t in obj.tracks:
            try:
                val = getattr(t, "reprojection_error", None)
                if val is None:
                    continue
                err = float(val)
                if math.isfinite(err) and err >= 0.0:
                    out.append((t.name, err))
            except Exception:
                continue
    return out

# ---------------------------------------------------------------------
# Öffentliche API – selektiert nur, speichert Track-Namen
# ---------------------------------------------------------------------
def run_projection_cleanup_builtin(
    context: bpy.types.Context,
    *,
    wait_for_error: bool = False,    # obsolet hier; behalten für API-Kompatibilität
    timeout_s: float = 20.0,         # obsolet hier; behalten für API-Kompatibilität
) -> Dict[str, Any]:
    """
    Selektiert die fehlerstärksten Tracks und speichert deren Namen in scene['tco_proj_spike_tracks'].
    Es werden **keine** Tracks/Marker gelöscht.

    Anzahl-Selektion:
        error_basis = scene['error_track']
        error_T     = max(track.reprojection_error)
        n_select    = ceil(error_T / error_basis)

    Rückgabe:
        {
          "status": "OK" | "SKIPPED",
          "error_basis": float | None,
          "error_T": float | None,
          "n_total": int,
          "n_selected": int,
          "selected_names": List[str],
          "store_key": "tco_proj_spike_tracks",
        }
    """
    clip = _active_clip(context)
    if not clip:
        return {"status": "SKIPPED", "reason": "no_active_clip"}

    # 1) Reprojection-Error pro Track erfassen
    errs = _compute_track_errors(clip)
    n_total = len(errs)
    if n_total == 0:
        return {"status": "SKIPPED", "reason": "no_track_errors", "n_total": 0}

    # 2) Basis und T berechnen
    scene = getattr(context, "scene", None)
    error_basis = _scene_error_basis(scene)
    if not (isinstance(error_basis, (int, float)) and error_basis > 0):
        # defensiver Default: 1.0 → minimal selektieren, aber nicht explodieren
        error_basis = 1.0

    error_T = max(e for _, e in errs)
    n_select = max(1, int(math.ceil(float(error_T) / float(error_basis))))

    # 3) Sortieren & Top-N wählen
    errs.sort(key=lambda kv: kv[1], reverse=True)
    selected = errs[:n_select]
    selected_names = [name for name, _ in selected]

    # 4) UI-Selektion setzen (optional, hilfreich fürs Debugging)
    #    Vorher: alles deselecten
    try:
        for t in _iter_tracks(clip):
            t.select = False
        for t in _iter_tracks(clip):
            if t.name in selected_names:
                t.select = True
    except Exception:
        pass

    # 5) Persistenz für Folgeschritt
    try:
        scene[_STORE_TRACKS_KEY] = selected_names  # Übergabe an projektion_spike_filter_cycle
    except Exception:
        # Fallback: ignorieren, Rückgabe enthält trotzdem Liste
        pass

    return {
        "status": "OK",
        "error_basis": float(error_basis),
        "error_T": float(error_T),
        "n_total": int(n_total),
        "n_selected": int(len(selected_names)),
        "selected_names": selected_names,
        "store_key": _STORE_TRACKS_KEY,
    }
