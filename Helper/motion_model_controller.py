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
- Track-lokale Zähler (survival) & Metadaten in Custom-Props

Integration
- Vor dem Tracking-Zyklus pro Track aufrufen
- Optional: Nach dem Tracking mit frischen Stats erneut evaluieren

Abhängigkeiten (leichtgewichtig):
- ..Helper.util_format: fmt8
- Blender API: bpy

Hinweis zu Stats:
- Wir erwarten ein Stats-Dict je Track:
  {
    "error": float|None,           # Re-Projection/Track-Error (avg)
    "corr": float|None,            # Patch-Korrelation [0..1] (optional)
    "delta_scale": float|None,     # relative Skalierung (optional)
    "delta_rot": float|None,       # Rotation in Grad (optional)
    "survival": int|None           # stabil durchlaufene Frames seit letztem Switch
  }
- Fehlen Werte, greift die Logik defensiv (nur verfügbares Signal).
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

# Blender-Enum-Werte (robust ermittelt, inkl. Fallback auf kanonische Strings).
BLENDER_MODELS_ORDERED = [
    "Loc",           # Translation only
    "LocRot",        # + Rotation
    "LocRotScale",   # + Scale
    "Affine",        # + Shear
    "Perspective",   # volle Homographie
]

# Manche Builds führen auch "LocScale" (selten genutzt). Wir tolerieren es:
KNOWN_ALIASES = {
    "Location": "Loc",
    "Translation": "Loc",
    "LocScale": "LocRotScale",  # pragmatisch nach oben mappen
}

# Scene-Key-Defaults (konservativ, produktionstauglich)
SCENE_KEYS = {
    "kaiserlich_model_error_high": 1.5,   # ab hier Upgrade anstoßen
    "kaiserlich_model_error_crit": 2.5,   # harter Upgrade-Trigger
    "kaiserlich_model_corr_low":  0.60,   # unterhalb dessen eskalieren
    "kaiserlich_model_ds_mid":    0.15,   # ΔScale mittlere Schwelle
    "kaiserlich_model_ds_high":   0.25,   # ΔScale hohe Schwelle
    "kaiserlich_model_dr_mid":    15.0,   # ΔRot mittlere Schwelle (Grad)
    "kaiserlich_model_dr_high":   25.0,   # ΔRot hohe Schwelle (Grad)
    "kaiserlich_model_stable":    40,     # Frames stabile Phase für Downgrade
    "kaiserlich_model_low_err":   0.50,   # für Downgrade: Error deutlich klein
    "kaiserlich_model_high_cap":  1,      # 1=Perspective erlaubt, 0=Deckel Affine
}

# Track-lokale Custom-Props
TP_SURVIVAL   = "kaiserlich_model_survival"
TP_LAST_MODEL = "kaiserlich_model_last"
TP_LAST_FRAME = "kaiserlich_model_last_switch"


# ---------------------------------------------------------------------------
# Utility: Scene-Parameter lesen (mit Fallbacks)
# ---------------------------------------------------------------------------

def _get_scene_cfg(scene: bpy.types.Scene) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    for k, dflt in SCENE_KEYS.items():
        try:
            cfg[k] = getattr(scene, k, dflt)
            if cfg[k] is None:
                cfg[k] = dflt
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
        # Fallback Kaskade nach unten, falls Enum in Build nicht unterstützt
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
    # Deckel auf "Affine"
    if model == "Perspective":
        return "Affine"
    return model


# ---------------------------------------------------------------------------
# Kernlogik: Auswahl anhand Stats + Hysterese
# ---------------------------------------------------------------------------

def select_motion_model_for_track(
    track: bpy.types.MovieTrackingTrack,
    stats: Dict[str, Optional[float]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
) -> str:
    """
    Ermittelt das *empfohlene* Modell (setzt es noch nicht).
    Nutzt Scene-CFG (Thresholds), Survival-Zähler (Track-Custom-Prop) und
    die gelieferten Stats (error/corr/delta_scale/delta_rot/survival).
    """
    scene = scene or bpy.context.scene
    cfg = _get_scene_cfg(scene)

    e  = stats.get("error")
    c  = stats.get("corr")
    ds = stats.get("delta_scale")
    dr = stats.get("delta_rot")

    # Survival aus Stats bevorzugen; sonst aus Track-Prop; ansonsten 0
    survival = stats.get("survival")
    if survival is None:
        survival = int(track.get(TP_SURVIVAL, 0))

    allow_persp = bool(cfg["kaiserlich_model_high_cap"] == 1)

    model_now = _current_model(track)
    rank_now  = _model_rank(model_now)

    # --- Upgrade-Trigger -----------------------------------------------------
    need_upgrade = False
    target_rank  = rank_now

    if e is not None and e >= cfg["kaiserlich_model_error_crit"]:
        # Harte Eskalation um 2 Stufen (wo möglich)
        target_rank = min(rank_now + 2, len(BLENDER_MODELS_ORDERED) - 1)
        need_upgrade = True
    else:
        # Weiche Eskalation (eine Stufe), wenn Error hoch oder Corr niedrig
        if (e is not None and e >= cfg["kaiserlich_model_error_high"]) or \
           (c is not None and c <= cfg["kaiserlich_model_corr_low"]):
            target_rank = min(rank_now + 1, len(BLENDER_MODELS_ORDERED) - 1)
            need_upgrade = True

        # Zusätzliche Eskalation basierend auf Bewegungsdynamik
        if not need_upgrade and (ds is not None or dr is not None):
            ds_mid  = cfg["kaiserlich_model_ds_mid"]
            ds_high = cfg["kaiserlich_model_ds_high"]
            dr_mid  = cfg["kaiserlich_model_dr_mid"]
            dr_high = cfg["kaiserlich_model_dr_high"]

            high_motion = (ds is not None and ds >= ds_high) or (dr is not None and dr >= dr_high)
            mid_motion  = (ds is not None and ds >= ds_mid)  or (dr is not None and dr >= dr_mid)

            if high_motion:
                target_rank = max(target_rank, min(rank_now + 2, len(BLENDER_MODELS_ORDERED) - 1))
                need_upgrade = True
            elif mid_motion:
                target_rank = max(target_rank, min(rank_now + 1, len(BLENDER_MODELS_ORDERED) - 1))
                need_upgrade = True

    # Deckel anwenden
    target_model = BLENDER_MODELS_ORDERED[target_rank]
    target_model = _cap_highest_model(target_model, allow_persp)

    # --- Downgrade-Trigger (Hysterese) --------------------------------------
    if not need_upgrade:
        # Stabilitätsfenster prüfen
        stable_frames = int(cfg["kaiserlich_model_stable"])
        low_err       = float(cfg["kaiserlich_model_low_err"])
        if survival >= stable_frames and (e is None or e <= low_err) and (c is None or c >= 0.80):
            # Eine Stufe entspannen
            target_rank = max(rank_now - 1, 0)
            target_model = BLENDER_MODELS_ORDERED[target_rank]

    return target_model


def apply_adaptive_model(
    track: bpy.types.MovieTrackingTrack,
    stats: Dict[str, Optional[float]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
    log: bool = True,
) -> bool:
    """
    Wendet das adaptiv empfohlene Modell sofort an.
    Pflegt zudem Survival-Zähler & Metadaten in Track-Custom-Props.
    """
    scene = scene or bpy.context.scene
    model_now = _current_model(track)
    model_new = select_motion_model_for_track(track, stats, scene, frame_current)

    changed = False
    if model_new != model_now:
        ok = _set_motion_model_safe(track, model_new)
        changed = bool(ok)
        # Reset Survival, Switch-Marker setzen
        track[TP_SURVIVAL] = 0
        if frame_current is not None:
            track[TP_LAST_FRAME] = int(frame_current)
        track[TP_LAST_MODEL] = model_new
        if log:
            print(fmt8(f"[AdaptiveModel] {track.name}: {model_now} → {model_new} | stats={stats}"))
    else:
        # Stabilitätszähler erhöhen
        cur = int(track.get(TP_SURVIVAL, 0))
        track[TP_SURVIVAL] = cur + 1

    return changed


def apply_adaptive_models_for_tracks(
    tracks: Iterable[bpy.types.MovieTrackingTrack],
    per_track_stats: Dict[str, Dict[str, Optional[float]]],
    scene: Optional[bpy.types.Scene] = None,
    frame_current: Optional[int] = None,
    log: bool = True,
) -> int:
    """
    Batch-Anwendung über mehrere Tracks. per_track_stats keyed by track.name
    Return: Anzahl geänderter Modelle.
    """
    scene = scene or bpy.context.scene
    changed_total = 0
    for tr in tracks:
        stats = per_track_stats.get(tr.name, {})
        if apply_adaptive_model(tr, stats, scene, frame_current, log=log):
            changed_total += 1
    if log and changed_total:
        print(fmt8(f"[AdaptiveModel][Batch] Changed models: {changed_total}"))
    return changed_total


# ---------------------------------------------------------------------------
# Optionale Hilfen: Minimalanalyse, falls externe Stats fehlen
# (Konservativ & robust – nutzt nur verfügbare Infos)
# ---------------------------------------------------------------------------

def quick_stats_from_track(
    track: bpy.types.MovieTrackingTrack,
    window: int = 8,
) -> Dict[str, Optional[float]]:
    """
    Leichte Heuristik, wenn keine externen Metriken vorliegen.
    - error: track.average_error (falls verfügbar)
    - corr:  None (nicht zuverlässig ohne Patch-Korrelation)
    - delta_scale/rot: None (ohne Pattern-Geometrie konservativ)
    - survival: aus Track-Prop
    """
    try:
        err = float(getattr(track, "average_error", None))
    except Exception:
        err = None
    survival = int(track.get(TP_SURVIVAL, 0))
    return {
        "error": err,
        "corr": None,
        "delta_scale": None,
        "delta_rot": None,
        "survival": survival,
    }
