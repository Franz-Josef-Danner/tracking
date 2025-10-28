# Helper/motion_model_controller.py
# -*- coding: utf-8 -*-
"""
Adaptive Motion-Model-Steuerung für Blender Movie Tracking (Kaiserlich Tracker)

Kernfeatures
- Eskalationsleiter: Loc → LocRot → LocRotScale → Affine → Perspective
- Hysterese: Downgrade erst nach stabiler Phase
- Hard-Failsafe: Sofortiges Upgrade bei kritischen Fehlern
- Szenen-Parameter (über Scene-Custom-Props) mit robusten Defaults
- Sauberes Logging via fmt8()
- State-Speicherung pro Track auf MovieClip (Fallback: Scene), NICHT auf Track!

Erwartete Stats pro Track:
{
  "error": float|None,
  "corr": float|None,
  "delta_scale": float|None,
  "delta_rot": float|None,      # in Grad
  "survival": int|None
}
"""

from __future__ import annotations
import bpy
from typing import Dict, Any, Iterable, Optional

try:
    from ..Helper.util_format import fmt8
except Exception:
    def fmt8(x: Any) -> str:
        return f"{x}"

# ---------------------------------------------------------------------------
# Konstanten & Mapping
# ---------------------------------------------------------------------------

BLENDER_MODELS_ORDERED = [
    "Loc",           # Translation only
    "LocRot",        # + Rotation
    "LocRotScale",   # + Scale
    "Affine",        # + Shear
    "Perspective",   # volle Homographie
]

KNOWN_ALIASES = {
    "Location": "Loc",
    "Translation": "Loc",
    "LocScale": "LocRotScale",
}

SCENE_KEYS = {
    "kaiserlich_model_error_high": 1.5,   # Upgrade-Trigger (weich)
    "kaiserlich_model_error_crit": 2.5,   # Upgrade-Trigger (hart) +2 Stufen
    "kaiserlich_model_corr_low":  0.60,   # Korrelation zu niedrig -> Upgrade
    "kaiserlich_model_ds_mid":    0.15,   # ΔScale mittlere Schwelle
    "kaiserlich_model_ds_high":   0.25,   # ΔScale hohe Schwelle
    "kaiserlich_model_dr_mid":    15.0,   # ΔRot mittlere Schwelle (Grad)
    "kaiserlich_model_dr_high":   25.0,   # ΔRot hohe Schwelle (Grad)
    "kaiserlich_model_stable":    40,     # Frames für Downgrade (Hysterese)
    "kaiserlich_model_low_err":   0.50,   # Error-Grenze für Downgrade
    "kaiserlich_model_high_cap":  1,      # 1=Perspective erlaubt, 0=Cap auf Affine
}

# State-Namespace (auf MovieClip/Scene als flache IDProps)
PFX = "kaiserlich_model"
def _k(key: str, track_name: str) -> str:
    return f"{PFX}_{key}_{track_name}"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _get_scene_cfg(scene: bpy.types.Scene) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    for k, dflt in SCENE_KEYS.items():
        try:
            val = getattr(scene, k, dflt)
            cfg[k] = (dflt if val is None else val)
        except Exception:
            cfg[k] = dflt
    return cfg


def _normalize_model_name(name: str) -> str:
    if not name:
        return "Loc"
    if name in BLENDER_MODELS_ORDERED:
        return name
    return KNOWN_ALIASES.get(name, name if name in BLENDER_MODELS_ORDERED else "Loc")


def _set_motion_model_safe(track: bpy.types.MovieTrackingTrack, model: str) -> bool:
    model_n = _normalize_model_name(model)
    try:
        track.motion_model = model_n
        return True
    except Exception:
        for candidate in reversed(BLENDER_MODELS_ORDERED):
            try:
                track.motion_model = candidate
                return True
            except Exception:
                continue
    return False


def _current_model(track: bpy.types.MovieTrackingTrack) -> str:
    try:
        return _normalize_model_name(track.motion_model)
    except Exception:
        return "Loc"


def _model_rank(model: str) -> int:
    try:
        return BLENDER_MODELS_ORDERED.index(_normalize_model_name(model))
    except Exception:
        return 0


def _cap_highest_model(model: str, allow_perspective: bool) -> str:
    if allow_perspective:
        return model
    return "Affine" if model == "Perspective" else model


def _resolve_clip(track: bpy.types.MovieTrackingTrack) -> Optional[bpy.types.MovieClip]:
    try:
        return getattr(bpy.context.space_data, "clip", None)
    except Exception:
        return None


def _idprops_supported(x) -> bool:
    try:
        getattr(x, "keys")
        x["__probe__"] = 1
        del x["__probe__"]
        return True
    except Exception:
        return False


def _get_state(key: str, track_name: str, clip=None, scene=None, default=None):
    if clip is not None and _idprops_supported(clip):
        k = _k(key, track_name)
        if k in clip:
            return clip[k]
    if scene is not None and _idprops_supported(scene):
        k = _k(key, track_name)
        if k in scene:
            return scene[k]
    return default


def _set_state(key: str, track_name: str, value, clip=None, scene=None):
    if clip is not None and _idprops_supported(clip):
        clip[_k(key, track_name)] = value
        return
    if scene is not None and _idprops_supported(scene):
        scene[_k(key, track_name)] = value
        return
    # sonst silent no-op

# ---------------------------------------------------------------------------
# Kernlogik
# ---------------------------------------------------------------------------

def select_motion_model_for_track(
    track: bpy.types.MovieTrackingTrack,
    stats: Dict[str, Optional[float]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
    clip: Optional[bpy.types.MovieClip] = None,
) -> str:
    """Bestimme das Zielmodell (setzt es nicht)."""
    scene = scene or bpy.context.scene
    cfg = _get_scene_cfg(scene)

    e  = stats.get("error")
    c  = stats.get("corr")
    ds = stats.get("delta_scale")
    dr = stats.get("delta_rot")

    survival = stats.get("survival")
    if survival is None:
        survival = int(_get_state("survival", track.name, clip=clip, scene=scene, default=0) or 0)

    allow_persp = bool(cfg["kaiserlich_model_high_cap"] == 1)

    model_now = _current_model(track)
    rank_now  = _model_rank(model_now)

    # Upgrade
    need_upgrade = False
    target_rank = rank_now

    if e is not None and e >= cfg["kaiserlich_model_error_crit"]:
        target_rank = min(rank_now + 2, len(BLENDER_MODELS_ORDERED) - 1)
        need_upgrade = True
    else:
        if (e is not None and e >= cfg["kaiserlich_model_error_high"]) or \
           (c is not None and c <= cfg["kaiserlich_model_corr_low"]):
            target_rank = min(rank_now + 1, len(BLENDER_MODELS_ORDERED) - 1)
            need_upgrade = True

        if not need_upgrade and (ds is not None or dr is not None):
            ds_mid, ds_high = cfg["kaiserlich_model_ds_mid"], cfg["kaiserlich_model_ds_high"]
            dr_mid, dr_high = cfg["kaiserlich_model_dr_mid"], cfg["kaiserlich_model_dr_high"]
            high_motion = (ds is not None and ds >= ds_high) or (dr is not None and dr >= dr_high)
            mid_motion  = (ds is not None and ds >= ds_mid)  or (dr is not None and dr >= dr_mid)
            if high_motion:
                target_rank = max(target_rank, min(rank_now + 2, len(BLENDER_MODELS_ORDERED) - 1))
                need_upgrade = True
            elif mid_motion:
                target_rank = max(target_rank, min(rank_now + 1, len(BLENDER_MODELS_ORDERED) - 1))
                need_upgrade = True

    target_model = _cap_highest_model(BLENDER_MODELS_ORDERED[target_rank], allow_persp)

    # Downgrade (Hysterese)
    if not need_upgrade:
        stable_frames = int(cfg["kaiserlich_model_stable"])
        low_err = float(cfg["kaiserlich_model_low_err"])
        if survival >= stable_frames and (e is None or e <= low_err) and (c is None or c >= 0.80):
            target_rank = max(rank_now - 1, 0)
            target_model = BLENDER_MODELS_ORDERED[target_rank]

    return target_model


def apply_adaptive_model(
    track: bpy.types.MovieTrackingTrack,
    stats: Dict[str, Optional[float]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
    log: bool = True,
    clip: Optional[bpy.types.MovieClip] = None,
) -> bool:
    """Setze das adaptiv empfohlene Modell und pflege State am Clip/Scene."""
    scene = scene or bpy.context.scene
    if clip is None:
        clip = _resolve_clip(track)

    model_now = _current_model(track)
    model_new = select_motion_model_for_track(track, stats, scene, frame_current, clip=clip)

    changed = False
    if model_new != model_now:
        ok = _set_motion_model_safe(track, model_new)
        changed = bool(ok)
        _set_state("survival", track.name, 0, clip=clip, scene=scene)
        if frame_current is not None:
            _set_state("last_switch", track.name, int(frame_current), clip=clip, scene=scene)
        _set_state("last_model", track.name, model_new, clip=clip, scene=scene)
        if log:
            print(fmt8(f"[AdaptiveModel] {track.name}: {model_now} → {model_new} | stats={stats}"))
    else:
        cur = int(_get_state("survival", track.name, clip=clip, scene=scene, default=0) or 0)
        _set_state("survival", track.name, cur + 1, clip=clip, scene=scene)

    return changed


def apply_adaptive_models_for_tracks(
    tracks: Iterable[bpy.types.MovieTrackingTrack],
    per_track_stats: Dict[str, Dict[str, Optional[float]]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
    log: bool = True,
    clip: Optional[bpy.types.MovieClip] = None,
) -> int:
    """Batch-Anwendung. Return: Anzahl geänderter Modelle."""
    scene = scene or bpy.context.scene
    changed_total = 0
    for tr in tracks:
        stats = per_track_stats.get(tr.name, {})
        if apply_adaptive_model(tr, stats, scene, frame_current, log=log, clip=clip):
            changed_total += 1
    if log and changed_total:
        print(fmt8(f"[AdaptiveModel][Batch] Changed models: {changed_total}"))
    return changed_total


# ---------------------------------------------------------------------------
# Minimal-Stats (fallback), wenn keine externen Metriken vorliegen
# ---------------------------------------------------------------------------

def quick_stats_from_track(
    track: bpy.types.MovieTrackingTrack,
    window: int = 8,
) -> Dict[str, Optional[float]]:
    """Leichte Heuristik (nutzt average_error + gespeicherten Survival-State)."""
    try:
        err = float(getattr(track, "average_error", None))
    except Exception:
        err = None
    scene = bpy.context.scene
    clip = _resolve_clip(track)
    survival = int(_get_state("survival", track.name, clip=clip, scene=scene, default=0) or 0)
    return {
        "error": err,
        "corr": None,
        "delta_scale": None,
        "delta_rot": None,
        "survival": survival,
    }
