"""Scene properties + helpers for Repeat-Scope & Overlay-Anbindung."""

import bpy
from typing import Dict, Any

_KC_REPEAT_MAP_KEY = "kc_repeat_counts"     # Dict[int->int]
_KC_REPEAT_RADIUS_KEY = "kc_repeat_radius"  # Int


def get_or_init_scene_props(scene: bpy.types.Scene):
    return scene  # Platzhalter, falls du später eine PropertyGroup kapselst


def get_repeat_radius(scene: bpy.types.Scene) -> int:
    # Default 25 Frames, UI überschreibt via Panel
    return int(scene.get(_KC_REPEAT_RADIUS_KEY, 25))


def set_repeat_radius(scene: bpy.types.Scene, value: int) -> None:
    scene[_KC_REPEAT_RADIUS_KEY] = max(0, int(value))
    _notify_overlay_changed(scene)


def get_repeat_map(scene: bpy.types.Scene) -> Dict[int, int]:
    d = scene.get(_KC_REPEAT_MAP_KEY, {})
    # ID-Properties liefern dict[str, Any]; Schlüssel zurück auf int casten
    return {int(k): int(v) for k, v in d.items()} if isinstance(d, dict) else {}


def get_repeat_count(scene: bpy.types.Scene, frame: int) -> int:
    """Convenience: einzelnen Repeat-Count für Coordinator-Logging ermitteln."""
    return int(get_repeat_map(scene).get(int(frame), 0))


def set_repeat_map(scene: bpy.types.Scene, mapping: Dict[int, int]) -> None:
    # Nur positive Werte persistieren; Speichern als str->int
    compact = {str(int(k)): int(v) for k, v in mapping.items() if int(v) > 0}
    old = scene.get(_KC_REPEAT_MAP_KEY, {})
    if not isinstance(old, dict) or old != compact:
        scene[_KC_REPEAT_MAP_KEY] = compact
        _notify_overlay_changed(scene)


def merge_repeat_series(scene: bpy.types.Scene, series: Dict[int, int]) -> None:
    """Max-Merge: bestehende Counts behalten höheren Wert; atomar schreiben."""
    base = get_repeat_map(scene)
    fmin, fmax = int(scene.frame_start), int(scene.frame_end)
    for f, c in series.items():
        c = int(c)
        if c <= 0:
            continue
        if f < fmin or f > fmax:
            continue  # Off-Range konsequent verwerfen
        if f in base:
            if c > base[f]:
                base[f] = c
        else:
            base[f] = c
    set_repeat_map(scene, base)


def prune_repeat_map(scene: bpy.types.Scene) -> None:
    """Einmaliges Cleanup: entferne Off-Range- oder leere Keys."""
    fmin, fmax = int(scene.frame_start), int(scene.frame_end)
    pruned = {
        f: c for f, c in get_repeat_map(scene).items() if fmin <= f <= fmax and c > 0
    }
    set_repeat_map(scene, pruned)


def _notify_overlay_changed(scene: bpy.types.Scene) -> None:
    # Soft-Hook: Overlay zum Redraw anstupsen, ohne harten Import
    try:
        from ..ui.repeat_scope import request_overlay_redraw  # lazy import
        request_overlay_redraw(bpy.context)
    except Exception:
        pass

