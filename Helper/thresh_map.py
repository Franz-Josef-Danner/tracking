# Helper/thresh_map.py
# -----------------------------------------------------------------------------
# Threshold-Map pro Frame:
# - Speichert alle relevanten Threshold-Properties pro Frame.
# - Liefert "Skip-Entscheidung" für auto_calibrate, indem gespeicherte Werte
#   (exakt oder interpoliert) angewendet werden.
# - Backt bei zwei nahen Ankerpunkten (Abstand < frames_per_track) die
#   Zwischenwerte in die Map ein (Interpolation).
# -----------------------------------------------------------------------------

import bpy
from typing import Dict, List, Tuple, Optional

# Relevante Scene-Properties (müssen im Add-on angelegt sein)
THRESH_KEYS: Tuple[str, ...] = (
    "kaiserlich_rot_thresh_x",
    "kaiserlich_rot_thresh_y",
    "kaiserlich_scale_thresh_min",
    "kaiserlich_scale_thresh_max",
    "kaiserlich_rot_scale_thresh_rot",
    "kaiserlich_rot_scale_thresh_scale",
    "kaiserlich_perspective_thresh",
)

# Szene-Key unter dem die Map persistiert wird (ID-Property, verschachtelt)
SCENE_MAP_KEY = "kaiserlich_threshold_map"  # dict: {"frames": { "123": {prop:value,...}, ... }}


# --- Low-Level: Map holen/anlegen ------------------------------------------------

def _ensure_map(scene: bpy.types.Scene) -> Dict:
    """Sichert, dass die Szenen-Map existiert und hat Struktur {'frames': {...}}."""
    if SCENE_MAP_KEY not in scene:
        scene[SCENE_MAP_KEY] = {"frames": {}}
    mp = scene[SCENE_MAP_KEY]
    # Sicherheitsnetz für Altzustände
    if not isinstance(mp, dict):
        scene[SCENE_MAP_KEY] = {"frames": {}}
        mp = scene[SCENE_MAP_KEY]
    if "frames" not in mp or not isinstance(mp["frames"], dict):
        mp["frames"] = {}
    return mp


def _frames_dict(scene: bpy.types.Scene) -> Dict[str, Dict[str, float]]:
    return _ensure_map(scene)["frames"]


def clear_threshold_map(scene: bpy.types.Scene) -> None:
    """Optionale Utility zum Leeren (Debug/Reset)."""
    scene[SCENE_MAP_KEY] = {"frames": {}}


# --- IO: Scene-Thresholds lesen/schreiben ---------------------------------------

def _capture_current_thresholds(scene: bpy.types.Scene) -> Dict[str, float]:
    data: Dict[str, float] = {}
    for key in THRESH_KEYS:
        if hasattr(scene, key):
            try:
                data[key] = float(getattr(scene, key))
            except Exception:
                pass
    return data


def _apply_thresholds_to_scene(scene: bpy.types.Scene, values: Dict[str, float]) -> None:
    for key, val in values.items():
        if hasattr(scene, key):
            try:
                setattr(scene, key, float(val))
            except Exception:
                pass


def store_thresholds_for_frame(scene: bpy.types.Scene, frame: int, values: Optional[Dict[str, float]] = None) -> None:
    """Speichert gegebene oder aktuelle Scene-Thresholds unter frame."""
    frames = _frames_dict(scene)
    fkey = str(int(frame))
    if values is None:
        values = _capture_current_thresholds(scene)
    frames[fkey] = dict(values)  # flach, nur Primitives


def has_thresholds_for_frame(scene: bpy.types.Scene, frame: int) -> bool:
    return str(int(frame)) in _frames_dict(scene)


def get_thresholds_for_frame(scene: bpy.types.Scene, frame: int) -> Optional[Dict[str, float]]:
    return _frames_dict(scene).get(str(int(frame)))


# --- Nachbarn & Interpolation ----------------------------------------------------

def _sorted_frame_keys(scene: bpy.types.Scene) -> List[int]:
    frames = _frames_dict(scene)
    return sorted(int(k) for k in frames.keys())


def _neighbor_frames(scene: bpy.types.Scene, frame: int) -> Tuple[Optional[int], Optional[int]]:
    """
    Liefert (links, rechts) gespeicherte Frames um 'frame' herum.
    None, falls nicht vorhanden.
    """
    arr = _sorted_frame_keys(scene)
    if not arr:
        return None, None
    left = None
    right = None
    for f in arr:
        if f <= frame:
            left = f
        if f >= frame:
            right = f
            break
    # Feinschliff: wenn erster gespeicherter Frame > frame => left=None, right=erster
    # wenn letzter gespeicherter Frame < frame => left=letzter, right=None
    if right is None and arr:
        # everything < frame
        right = None
    return left, right


def _linear_interpolate(a: float, b: float, t: float) -> float:
    return a * (1.0 - t) + b * t


def _interpolate_threshold_sets(v0: Dict[str, float], v1: Dict[str, float], t: float) -> Dict[str, float]:
    out: Dict[str, float] = {}
    # Nur Keys interpolieren, die in beiden vorhanden sind
    keys = set(v0.keys()).intersection(v1.keys())
    for k in keys:
        try:
            out[k] = _linear_interpolate(float(v0[k]), float(v1[k]), float(t))
        except Exception:
            # Fallback: falls Konvertierung schiefgeht, nimm v0
            out[k] = v0[k]
    # Wenn Keys nur auf einer Seite existieren, konservativ v0-Wert übernehmen
    for k in set(v0.keys()) - keys:
        out[k] = v0[k]
    for k in set(v1.keys()) - keys:
        # Option: ebenfalls übernehmen – hier ignorieren, damit konsistent
        pass
    return out


def _frames_per_track(scene: bpy.types.Scene) -> int:
    # UI/Scene-Prop muss existieren: "kaiserlich_frames_per_track"
    val = getattr(scene, "kaiserlich_frames_per_track", 25)
    try:
        return max(1, int(val))
    except Exception:
        return 25


def _maybe_bake_close_range(scene: bpy.types.Scene, a: int, b: int) -> None:
    """
    Wenn |a-b| < frames_per_track: Interpolation für alle Frames [min, max]
    in die Map einbacken (inkl. Endpunkte). Dadurch werden zukünftige
    Playhead-Treffer ohne Tests bedient.
    """
    frames = _frames_dict(scene)
    fpt = _frames_per_track(scene)
    f0, f1 = (int(a), int(b)) if a <= b else (int(b), int(a))
    gap = f1 - f0
    if gap < 1:
        return
    if gap >= fpt:
        return

    v0 = frames.get(str(f0))
    v1 = frames.get(str(f1))
    if not v0 or not v1:
        return

    for f in range(f0, f1 + 1):
        t = (f - f0) / float(gap)
        interp = _interpolate_threshold_sets(v0, v1, t)
        frames[str(f)] = interp  # baken


# --- High-Level: Entscheidungslogik für Master ----------------------------------

def should_use_cached_thresholds(context: bpy.types.Context, frame: int) -> bool:
    """
    Entscheidung, ob auto_calibrate für 'frame' ausgelassen werden kann.
    Regeln:
    1) Exakter Treffer im Map-Cache -> apply + True (skip).
    2) Zwei Ankerframes um 'frame' herum vorhanden UND Abstand < frames_per_track
       -> Interpolation anwenden (+ in Map cachen) -> True (skip).
    3) Sonst False (kein Skip).
    """
    scene = context.scene
    # 1) Exakt gespeichert?
    if has_thresholds_for_frame(scene, frame):
        vals = get_thresholds_for_frame(scene, frame)
        if vals:
            _apply_thresholds_to_scene(scene, vals)
            print(f"[Kaiserlich Tracker][ThreshMap] Frame {frame}: gespeicherte Thresholds angewendet (exakt).")
            return True

    # 2) Nachbarn + Interpolation
    left, right = _neighbor_frames(scene, frame)
    if left is not None and right is not None and left != right:
        gap = abs(int(right) - int(left))
        if gap < _frames_per_track(scene):
            frames = _frames_dict(scene)
            v0 = frames.get(str(int(left)))
            v1 = frames.get(str(int(right)))
            if v0 and v1:
                # Interpolation on-the-fly
                t = (frame - float(left)) / float(gap)
                interp = _interpolate_threshold_sets(v0, v1, t)
                _apply_thresholds_to_scene(scene, interp)
                # Cache für diesen Frame setzen
                store_thresholds_for_frame(scene, frame, interp)
                print(f"[Kaiserlich Tracker][ThreshMap] Frame {frame}: interpolierte Thresholds angewendet (Anker {left}<->{right}, gap={gap}).")
                return True

    return False


def save_after_autocalibrate(context: bpy.types.Context, frame: int, bake_neighbors: bool = True) -> None:
    """
    Nach erfolgreichem auto_calibrate aufrufen:
    - aktuelle Scene-Thresholds unter 'frame' speichern
    - wenn naher Nachbar vorhanden (Abstand < frames_per_track), Spanne einbacken
    """
    scene = context.scene
    store_thresholds_for_frame(scene, frame)  # liest aktuelle Werte
    left, right = _neighbor_frames(scene, frame)

    if bake_neighbors:
        # Prüfe je eine Seite und backe ein, falls nah
        if left is not None and left != frame:
            _maybe_bake_close_range(scene, left, frame)
        if right is not None and right != frame:
            _maybe_bake_close_range(scene, frame, right)
