# SPDX-License-Identifier: GPL-2.0-or-later
"""
Utilities to reduce high-error tracks and inspect average reprojection error.
Provides run_reduce_error_tracks and get_avg_reprojection_error with diagnostic
logging.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import bpy

try:
    from .count import error_value  # robuste per-Track-Metrik
except Exception:  # pragma: no cover
    from ..Helper.count import error_value  # Fallback Pfad

__all__ = ("run_reduce_error_tracks", "get_avg_reprojection_error")


def _resolve_clip(context: bpy.types.Context):
    clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        clip = getattr(context, "edit_movieclip", None)
    if not clip and getattr(bpy.context, "edit_movieclip", None):
        clip = bpy.context.edit_movieclip
    return clip


def run_reduce_error_tracks(context) -> Dict[str, Any]:
    """
    Löscht oder mutet Tracks mit hohem Fehlerwert.
    Erwartet Scene-Property 'error_track' als Schwellwert.
    Rückgabe enthält Diagnose-Felder für Telemetrie.
    """
    scn = context.scene
    thr = float(scn.get("error_track", 2.0))
    clip = _resolve_clip(context)
    trk = getattr(clip, "tracking", None) if clip else None
    tracks = list(getattr(trk, "tracks", [])) if trk else []

    cand: List[Tuple[str, float]] = []
    for t in tracks:
        try:
            if getattr(t, "mute", False):
                continue
            ev = float(error_value(t))
            if ev >= thr:
                cand.append((t.name, ev))
        except Exception:
            pass
    cand.sort(key=lambda x: x[1], reverse=True)
    print(f"[ReduceDBG] reducer candidates: count={len(cand)} top10={[(n, round(e,4)) for n,e in cand[:10]]}")

    require_selected = bool(scn.get("reduce_only_selected", False))
    if require_selected:
        cand = [(n, e) for (n, e) in cand if getattr(trk.tracks.get(n), "select", False)]
        print(f"[ReduceDBG] reducer policy: require_selected=True → remaining={len(cand)}")
    else:
        print(f"[ReduceDBG] reducer policy: require_selected=False")

    do_mute = bool(scn.get("reduce_mute_instead_delete", False))
    print(f"[ReduceDBG] reducer action: {'MUTE' if do_mute else 'DELETE'} thr={thr}")

    deleted_names: List[str] = []
    count = 0
    for name, _e in cand:
        t = trk.tracks.get(name) if trk else None
        if not t:
            continue
        try:
            if do_mute:
                t.mute = True
            else:
                trk.tracks.remove(t)
            deleted_names.append(name)
            count += 1
        except Exception as _exc:
            print(f"[ReduceDBG] reducer failed for {name}: {_exc}")

    print(f"[ReduceDBG] reducer summary: affected={count}")
    return {
        "deleted": count,
        "names": deleted_names,
        "thr": thr,
        "policy": {
            "require_selected": require_selected,
            "mute_instead_delete": do_mute,
        },
        "candidates": cand[:50],
    }


def get_avg_reprojection_error(context: bpy.types.Context) -> Optional[float]:
    clip = _resolve_clip(context)
    if not clip:
        return None
    trk = getattr(clip, "tracking", None)
    obj = getattr(getattr(trk, "objects", None), "active", None) if trk else None
    try:
        if obj and obj.reconstruction and getattr(obj.reconstruction, "is_valid", False):
            ae = float(getattr(obj.reconstruction, "average_error", float("nan")))
            if ae == ae and ae > 0.0:
                return ae
    except Exception:
        pass
    try:
        if not obj:
            return None
        vals: List[float] = []
        for t in obj.tracks:
            try:
                v = float(error_value(t))
                if v >= 0.0:
                    vals.append(v)
            except Exception:
                pass
        if vals:
            return sum(vals) / len(vals)
    except Exception:
        pass
    return None
