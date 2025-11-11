# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Stabilisierung/Korrektur von Marker-Positionen im aktuellen Frame
# anhand stabiler Referenzen aus bis zu 4 Rückblick-Frames.
# Kompatibel mit:
#   - Szene-String "good_marker" ODER "best_marker" (mutual exclusive)
#   - Optionalen UUID-Maps: "<key>_uuid_map" als String-Dict {uuid: name}
#
# Log-Ausgaben:
#   [FRAME]   – Aktueller Frame der Korrektur
#   [TRACK]   – Aktueller Trackname
#   [FORMULA] – Einzelwerte (Gewicht, Distanz, Velocity)
#   [TRIM]    – Trimmed Mean (Samples, Ratio, Endmittel)
#   [RESULT]  – Alte vs neue Markerposition
#   [WARN]    – Abbruch oder unvollständige Referenzen
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple, Dict, Any
import bpy
import ast
import math


# ============================================================
# Low-level Marker Utilities
# ============================================================

def _find_marker_at_frame(track, frame: int):
    try:
        mk = track.markers.find_frame(int(frame))
        return mk if mk and not mk.mute else None
    except Exception:
        return None


def marker_exists(track, frame: int) -> bool:
    return _find_marker_at_frame(track, frame) is not None


def get_marker_position(track, frame: int) -> Tuple[float, float]:
    mk = _find_marker_at_frame(track, frame)
    if mk:
        return float(mk.co[0]), float(mk.co[1])
    head = track.markers[0] if track.markers else None
    return (float(head.co[0]), float(head.co[1])) if head else (0.0, 0.0)


def set_marker_position(track, frame: int, x: float, y: float):
    mk = _find_marker_at_frame(track, frame)
    if mk:
        mk.co[0] = float(x)
        mk.co[1] = float(y)


def _active_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    wm = getattr(context, "window_manager", None)
    if not wm:
        return None
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'CLIP_EDITOR':
                sp = area.spaces.active
                if sp and getattr(sp, "clip", None):
                    return sp.clip
    return None


def _iter_active_tracks_at_frame(context, frame: int):
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr


def get_active_markers(context, frame: Optional[int]):
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))


# ============================================================
# Referenzmanagement (good_marker / best_marker)
# ============================================================

def _read_scene_string(scene: bpy.types.Scene, key: str) -> Optional[List[str]]:
    if key not in scene:
        return None
    raw = list(scene[key])
    out = []
    for v in raw:
        if isinstance(v, str):
            out.append(v)
        else:
            try:
                out.append(str(v))
            except Exception:
                pass
    return out


def _detect_uuid_mode(values: List[str]) -> bool:
    if not values:
        return False
    def _is_uuid(s: str) -> bool:
        return isinstance(s, str) and "-" in s and len(s) >= 30
    return all(_is_uuid(v) for v in values)


def _load_uuid_map(scene: bpy.types.Scene, key: str) -> Dict[str, str]:
    map_key = f"{key}_uuid_map"
    if map_key not in scene:
        return {}
    try:
        data = ast.literal_eval(scene[map_key])
        if isinstance(data, dict):
            return {str(u): str(n) for u, n in data.items()}
    except Exception:
        pass
    return {}


def _select_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    has_good = "good_marker" in scene
    has_best = "best_marker" in scene
    if has_good and has_best:
        print("[MarkerCorrection][WARN] Beide Referenz-Sets vorhanden – Konflikt.")
        return None
    if not has_good and not has_best:
        print("[MarkerCorrection][WARN] Kein Referenz-Set vorhanden.")
        return None
    return "good_marker" if has_good else "best_marker"


def _build_reference_name_set(context: bpy.types.Context,
                              scene: bpy.types.Scene) -> Optional[Dict[str, Any]]:
    key = _select_reference_key(scene)
    if key is None:
        return None
    ref_values = _read_scene_string(scene, key)
    if not ref_values:
        print(f"[MarkerCorrection][WARN] Szene-String {key} ist leer.")
        return None
    is_uuid = _detect_uuid_mode(ref_values)
    uuid_to_name = _load_uuid_map(scene, key) if is_uuid else {}

    clip = _active_clip(context)
    if not clip:
        name_set = set(uuid_to_name.values()) if is_uuid else set(ref_values)
    else:
        scene_names = {t.name for t in clip.tracking.tracks}
        if is_uuid and uuid_to_name:
            mapped_names = set(uuid_to_name.get(uid, "") for uid in ref_values)
            name_set = {n for n in mapped_names if n and n in scene_names}
        elif is_uuid and not uuid_to_name:
            name_set = set()
        else:
            name_set = {n for n in ref_values if n in scene_names}

    return {
        "key": key,
        "is_uuid": is_uuid,
        "ref_values": ref_values,
        "uuid_to_name": uuid_to_name,
        "name_set": name_set,
    }


# ============================================================
# Mathe / Robustheit
# ============================================================

def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _radial_weight(p_target: Tuple[float, float],
                   p_ref: Tuple[float, float],
                   eps: float = 1e-6) -> float:
    d2 = _dist2(p_target, p_ref)
    w = 1.0 / (eps + math.sqrt(d2))
    print(f"[MarkerCorrection][FORMULA] weight={w:.4f}  dist={math.sqrt(d2):.6f}")
    return w


def _trimmed_weighted_mean(vals: List[Tuple[float, float]],
                           weights: List[float],
                           trim_ratio: float = 0.10) -> Tuple[float, float]:
    n = len(vals)
    if n == 0:
        return 0.0, 0.0
    if n < 5:
        wsum = sum(weights) if weights else 0.0
        if wsum <= 0.0:
            return 0.0, 0.0
        vx = sum(v[0] * w for v, w in zip(vals, weights)) / wsum
        vy = sum(v[1] * w for v, w in zip(vals, weights)) / wsum
        print(f"[MarkerCorrection][TRIM] direct_mean  n={n}  vx={vx:.6f}  vy={vy:.6f}")
        return vx, vy

    # Sortiere nach Gewicht und trimme Extremwerte
    combined = sorted(zip(vals, weights), key=lambda x: (x[0][0]**2 + x[0][1]**2))
    k = max(1, int(n * trim_ratio))
    trimmed = combined[k:-k] if n > 2 * k else combined
    vals_t, w_t = zip(*trimmed)
    wsum = sum(w_t)
    if wsum <= 0.0:
        return 0.0, 0.0
    vx = sum(v[0] * w for v, w in zip(vals_t, w_t)) / wsum
    vy = sum(v[1] * w for v, w in zip(vals_t, w_t)) / wsum
    print(f"[MarkerCorrection][TRIM] n={n} trim={trim_ratio*100:.1f}%  → vx={vx:.6f} vy={vy:.6f}")
    return vx, vy


# ============================================================
# Hauptfunktion
# ============================================================

def correct_marker_positions(scene: bpy.types.Scene,
                             good_markers,
                             selected_markers,
                             frame_a: int,
                             frame_b: int,
                             frame_c: Optional[int] = None,
                             frame_d: Optional[int] = None):
    """
    Korrigiert instabile Markerpositionen anhand stabiler Referenzen
    aus bis zu 4 vorherigen Frames.
    """
    ctx = bpy.context
    print(f"[MarkerCorrection][FRAME] {frame_b}")

    ref_info = _build_reference_name_set(ctx, scene)
    if not ref_info:
        print("[MarkerCorrection][WARN] Keine Referenzen gefunden – Abbruch.")
        return

    clip = _active_clip(ctx)
    if not clip:
        print("[MarkerCorrection][WARN] Kein aktiver Clip – Abbruch.")
        return

    ref_names = ref_info["name_set"]
    all_tracks = {t.name: t for t in clip.tracking.tracks}

    for tr in selected_markers:
        if tr.name not in all_tracks:
            continue

        print(f"[MarkerCorrection][TRACK] {tr.name}")
        if not marker_exists(tr, frame_b):
            print("[MarkerCorrection][WARN] Kein Marker im Ziel-Frame – Skip.")
            continue

        p_cur = get_marker_position(tr, frame_b)
        velocities = []
        weights = []

        for f_prev in [frame_a, frame_c, frame_d]:
            if f_prev is None:
                continue
            if not marker_exists(tr, f_prev):
                continue
            p_prev = get_marker_position(tr, f_prev)
            vx = p_cur[0] - p_prev[0]
            vy = p_cur[1] - p_prev[1]
            w = _radial_weight(p_cur, p_prev)
            velocities.append((vx, vy))
            weights.append(w)

        if not velocities:
            print("[MarkerCorrection][WARN] Keine gültigen Rückblick-Frames.")
            continue

        vx, vy = _trimmed_weighted_mean(velocities, weights)
        new_pos = (p_cur[0] - vx, p_cur[1] - vy)
        set_marker_position(tr, frame_b, new_pos[0], new_pos[1])
        print(f"[MarkerCorrection][RESULT] old={p_cur}  new={new_pos}")
