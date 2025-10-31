# Helper/frame_value_cache.py
import bpy
import math
from typing import Dict, Optional, Tuple, List

CACHE_KEY = "kaiserlich_frame_cache"

# -----------------------------------------------------------------------------
# Interpolation ---------------------------------------------------------------
# -----------------------------------------------------------------------------
def _linear_interpolate(v1: float, v2: float, ratio: float) -> float:
    """Einfache lineare Interpolation zwischen v1 und v2."""
    return v1 + (v2 - v1) * ratio


# -----------------------------------------------------------------------------
# Cache-Verwaltung ------------------------------------------------------------
# -----------------------------------------------------------------------------
def get_cache(scene: bpy.types.Scene) -> Dict[str, Dict[str, float]]:
    """Lädt oder initialisiert den Frame-Cache."""
    cache = scene.get(CACHE_KEY, None)
    if cache is None or not isinstance(cache, dict):
        cache = {}
        scene[CACHE_KEY] = cache
    return cache


def save_frame_values(scene: bpy.types.Scene, frame: int, values: Dict[str, float], window: int = 50) -> None:
    """
    Speichert die Werte für den Frame und führt ggf. Interpolation zwischen benachbarten Frames durch.

    Args:
        scene: aktuelle Szene
        frame: aktueller Frame
        values: Dict mit Kategorie→Wert
        window: Frame-Abstand für Interpolationsprüfung
    """
    cache = get_cache(scene)
    f_key = str(frame)
    cache[f_key] = values.copy()

    # Nachbarn finden (links und rechts)
    neighbor_before, neighbor_after = None, None
    frames_sorted = sorted(int(k) for k in cache.keys())
    for f in frames_sorted:
        if f < frame and (frame - f) <= window:
            neighbor_before = f
        elif f > frame and (f - frame) <= window:
            neighbor_after = f
            break

    # Wenn beide Nachbarn existieren, Interpolation durchführen
    if neighbor_before and neighbor_after:
        v_before = cache[str(neighbor_before)]
        v_after = cache[str(neighbor_after)]
        span = neighbor_after - neighbor_before
        for f in range(neighbor_before + 1, neighbor_after):
            ratio = (f - neighbor_before) / span
            interp = {}
            for key in values.keys():
                if key in v_before and key in v_after:
                    interp[key] = _linear_interpolate(v_before[key], v_after[key], ratio)
            cache[str(f)] = interp

    scene[CACHE_KEY] = cache
    print(f"[FrameCache] 💾 Werte für Frame {frame} gespeichert (Keys={list(values.keys())})")
    if neighbor_before and neighbor_after:
        print(f"[FrameCache] 🔄 Interpolation von Frame {neighbor_before} → {neighbor_after} durchgeführt.")


def get_frame_values(scene: bpy.types.Scene, frame: int) -> Optional[Dict[str, float]]:
    """Lädt gespeicherte Werte für den Frame, falls vorhanden."""
    cache = scene.get(CACHE_KEY, {})
    return cache.get(str(frame))


def apply_cached_values(scene: bpy.types.Scene, frame: int) -> bool:
    """
    Trägt gespeicherte Werte in die Szenen-Properties ein.
    Gibt True zurück, wenn Werte gefunden und angewendet wurden.
    """
    data = get_frame_values(scene, frame)
    if not data:
        return False

    from .util_scene import set_scene_props
    props = {}
    if "rot_xy" in data:
        x = data["rot_xy"]
        y = min(1.0, x * (scene.render.resolution_x / max(1, scene.render.resolution_y)))
        props.update(kaiserlich_rot_thresh_x=x, kaiserlich_rot_thresh_y=y)
    if "scale" in data:
        s = data["scale"]
        props.update(
            kaiserlich_scale_thresh_min=s,
            kaiserlich_scale_thresh_max=min(1.0, s * 1.1)
        )
    if "rot_scale_rot" in data or "rot_scale_scale" in data:
        props.update(
            kaiserlich_rot_scale_thresh_rot=data.get("rot_scale_rot", 1.0),
            kaiserlich_rot_scale_thresh_scale=data.get("rot_scale_scale", 1.0)
        )
    if "perspective" in data:
        props["kaiserlich_perspective_thresh"] = data["perspective"]

    set_scene_props(scene, **props)
    print(f"[FrameCache] ♻️ Frame {frame}: Werte aus Cache angewendet ({list(data.keys())})")
    return True