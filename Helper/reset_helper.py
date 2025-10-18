import bpy
from typing import List, Dict, Any

# Gruppierte Threshold-Definitionen (Name optional, Hauptsache: props)
THRESH_LIST: List[Dict[str, Any]] = [
    {"group": "rotation", "props": [
        "kaiserlich_rot_thresh_x", "kaiserlich_rot_thresh_y"
    ]},
    {"group": "scale", "props": [
        "kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max"
    ]},
    {"group": "rot_scale", "props": [
        "kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"
    ]},
    {"group": "perspective", "props": [
        "kaiserlich_perspective_thresh"
    ]},
]


def get_scene_value(context: bpy.types.Context, prop: str) -> float:
    """Sicheren Zugriff auf eine Scene-Property geben.

    Gibt None zurück, wenn die Property nicht existiert.
    """
    scene = getattr(context, "scene", None)
    if scene is None:
        return None
    return getattr(scene, prop, None)


def set_scene_value(context: bpy.types.Context, prop: str, value: float) -> None:
    """Setzt eine Scene-Property, wenn sie existiert, ansonsten wird sie angelegt.
    Für die Verwendung in Tests ist direkter setattr ausreichend.
    """
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    try:
        setattr(scene, prop, float(value))
    except Exception:
        # defensive: ignoriere Schreibfehler
        pass


def reset_all_thresholds(context: bpy.types.Context, active_props: List[str]):
    """
    Setzt alle Threshold-Properties auf 1.0 (Neutralstellung), außer denen
    die in active_props angegeben sind.

    Wird nach jedem Trackinglauf ausgeführt, um Interferenzen zu vermeiden.
    """
    for t in THRESH_LIST:
        for p in t["props"]:
            if p not in active_props:
                set_scene_value(context, p, 1.0)
