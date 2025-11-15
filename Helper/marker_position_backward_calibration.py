# Helper/marker_position_backward_calibration.py
# ------------------------------------------------------------
# Rückwärts-Tracking Marker-Kalibrierung
# Spiegelung der forward-Kalibrierung, aber mit umgedrehten
# Frames, Velocity-Richtung und adaptiver Blend-Logik.
# ------------------------------------------------------------

from typing import Optional, Tuple, Dict, Any, Iterable, List
import ast
import bpy

_last_logged_values: Dict[str, str] = {}


# ------------------------------------------------------------
# Utility: Scene-Strings lesen / Logging / Track-Check
# (IDENTISCH wie Forward-Version)
# ------------------------------------------------------------

def _read_scene_string(scene: bpy.types.Scene, key: str):
    raw = scene.get(key)
    if raw is None:
        return None, 0
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            parsed = raw
    try:
        length = len(parsed)
    except Exception:
        length = 0
    return parsed, length


def _stringify_value_for_log(value: Any) -> str:
    try:
        if isinstance(value, dict):
            keys = sorted(map(str, value.keys()))
            return ",".join(keys)
        if isinstance(value, (list, tuple, set)):
            items = sorted(set(map(str, value)))
            return ",".join(items)
        s = str(value)
        return s.replace("\n", " ").replace("\r", " ")
    except Exception:
        return str(value)


def _log_if_changed(key: str, value: Any):
    content = _stringify_value_for_log(value).replace('"', "'")
    line = f"\"{key}\": \"{content}\""
    if _last_logged_values.get(key) != line:
        _last_logged_values[key] = line


def _compare_tracks_with_scene(scene: bpy.types.Scene, key: str, names: Iterable[str]):
    if not names:
        return

    clip = None
    try:
        space = bpy.context.space_data
        if space and getattr(space, "clip", None):
            clip = space.clip
    except Exception:
        pass

    if clip is None:
        try:
            clip = getattr(bpy.context, "edit_movieclip", None)
        except Exception:
            clip = None

    if clip is None:
        _log_if_changed(f"{key}_missing", ["<kein aktiver Clip>"])
        return

    try:
        scene_tracks = [t.name for t in clip.tracking.tracks]
    except Exception:
        _log_if_changed(f"{key}_missing", ["<tracking not accessible>"])
        return

    existing = [n for n in names if n in scene_tracks]
    missing = [n for n in names if n not in scene_tracks]
    if missing or len(existing) != len(names):
        _log_if_changed(f"{key}_missing", missing)
    else:
        if f"{key}_missing" in _last_logged_values:
            del _last_logged_values[f"{key}_missing"]


# ------------------------------------------------------------
# Active-Key Ermittlung (identisch zu Forward)
# ------------------------------------------------------------

def find_active_tracks_key(scene: bpy.types.Scene):
    meta = {
        'best': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
        'good': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
    }

    best_list, best_len = _read_scene_string(scene, "best_tracks")
    best_map, best_map_len = _read_scene_string(scene, "best_tracks_uuid_map")
    meta['best']['present']      = best_list is not None
    meta['best']['len']          = best_len
    meta['best']['has_uuid_map'] = best_map is not None
    meta['best']['map_len']      = best_map_len

    good_list, good_len = _read_scene_string(scene, "good_tracks")
    good_map, good_map_len = _read_scene_string(scene, "good_tracks_uuid_map")
    meta['good']['present']      = good_list is not None
    meta['good']['len']          = good_len
    meta['good']['has_uuid_map'] = good_map is not None
    meta['good']['map_len']      = good_map_len

    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"

    return active_key, meta


def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    key, _ = find_active_tracks_key(scene)
    return key


# ------------------------------------------------------------
# Erwartete extern bereitgestellte Funktionen
# ------------------------------------------------------------
# get_active_markers(frame)
# get_marker_position(track_or_name, frame)
# set_marker_position(track_or_name, frame, x, y)


# ------------------------------------------------------------
# Rückwärts-Kalibrierung (kritischer Teil)
# ------------------------------------------------------------

def correct_marker_positions_backward(
    scene: bpy.types.Scene,
    ref_tracks: List[str],
    calibrate_tracks: List[str],
    frame_now: int,
    frame_next: Optional[int],
    frame_next2: Optional[int] = None,
    frame_next3: Optional[int] = None
):
    """
    Rückwärts-Kalibrierung – jetzt vollständig symmetrisch zu Forward:
    - gleiche Referenzlogik („best“ bevorzugt, sonst „good“)
    - gleiche Filterlogik gegen Scene-Referenzen
    """

    # ------------------------------------------------------------
    # 1. Globale Referenz aus Szene lesen (Forward-Parität)
    # ------------------------------------------------------------
    ref_scene = None
    if "best_tracks" in scene:
        ref_scene = _read_scene_list(scene, "best_tracks") \
                    if callable(globals().get("_read_scene_list", None)) \
                    else None
    if not ref_scene and "good_tracks" in scene:
        ref_scene = _read_scene_list(scene, "good_tracks") \
                    if callable(globals().get("_read_scene_list", None)) \
                    else None

    # Falls gar keine Referenzen existieren → keine Kalibrierung
    if not ref_scene:
        return

    # Schnittmenge ref_tracks ∩ globale Referenzen
    ref_tracks = list(set(ref_tracks) & set(ref_scene))
    if not ref_tracks:
        return

    # Optionaler Dead-Reference Cleanup (identisch wie Forward)
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        real_names = {t.name for t in clip.tracking.tracks}
        ref_tracks = [t for t in ref_tracks if t in real_names]
    except Exception:
        return

    if not ref_tracks:
        return

    # ------------------------------------------------------------
    # 2. Mindestabdeckung
    # ------------------------------------------------------------
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    f0 = get_active_markers(frame_now)
    f1 = get_active_markers(frame_next)
    f2 = get_active_markers(frame_next2) if frame_next2 else []
    f3 = get_active_markers(frame_next3) if frame_next3 else []

    f0_good = [m for m in f0 if m in ref_tracks]
    f1_good = [m for m in f1 if m in ref_tracks]
    f2_good = [m for m in f2 if m in ref_tracks]
    f3_good = [m for m in f3 if m in ref_tracks]

    # Frame-Auswahl (exakt forward → invertiert)
    if len(f3_good) >= min_required:
        source = f3_good
        mode = 4
    elif len(f2_good) >= min_required:
        source = f2_good
        mode = 3
    elif len(f1_good) >= min_required:
        source = f1_good
        mode = 2
    else:
        return

    # ------------------------------------------------------------
    # 3. Clip-Aspect
    # ------------------------------------------------------------
    try:
        width = clip.size[0]
        height = clip.size[1]
        aspect_ratio = width / height if height else 1.0
    except Exception:
        aspect_ratio = 1.0

    # ------------------------------------------------------------
    # 4. Rückwärts-Prognose (Forward gespiegelte Logik)
    # ------------------------------------------------------------
    for tr in calibrate_tracks:
        x0, y0 = get_marker_position(tr, frame_now)
        x1, y1 = get_marker_position(tr, frame_next)

        wvx, wvy = [], []

        for gm in source:
            g0x, g0y = get_marker_position(gm, frame_now)
            g1x, g1y = get_marker_position(gm, frame_next)

            if mode >= 3:
                g2x, g2y = get_marker_position(gm, frame_next2)
            if mode == 4:
                g3x, g3y = get_marker_position(gm, frame_next3)

            # Velocity gespiegelte Forward-Formel
            if mode == 4:
                vx = 0.5 * ((g2x - g3x) + (g1x - g2x))
                vy = 0.5 * ((g2y - g3y) + (g1y - g2y))
            elif mode == 3:
                vx = 0.5 * ((g1x - g2x) + (g0x - g1x))
                vy = 0.5 * ((g1y - g2y) + (g0y - g1y))
            elif mode == 2:
                vx = (g1x - g0x)
                vy = (g1y - g0y)
            else:
                vx = vy = 0.0

            dx = (x0 - g0x)
            dy = (y0 - g0y)
            dist = (dx*dx + dy*dy) ** 0.5
            w = 1.0 / (1e-6 + dist)

            wvx.append((vx, w))
            wvy.append((vy, w))

        if not wvx:
            continue

        # Robust Mean (Forward identisch)
        def robust_mean(vw):
            if len(vw) < 5:
                sw = sum(w for v, w in vw)
                return (sum(v*w for v, w in vw) / sw) if sw else 0.0
            vs = sorted(vw, key=lambda x: x[0])
            cut = max(1, int(0.1 * len(vs)))
            trimmed = vs[cut:-cut] if len(vs) > 2*cut else vs
            sw = sum(w for v, w in trimmed)
            return (sum(v*w for v, w in trimmed) / sw) if sw else 0.0

        avg_vx = robust_mean(wvx)
        avg_vy = robust_mean(wvy)

        # Rückwärts-Prognose (spiegelbildlich zu Forward)
        pred_x = x1 - avg_vx
        pred_y = y1 - avg_vy

        diff_x = abs(x0 - pred_x)
        diff_y = abs(y0 - pred_y) * aspect_ratio

        wx = max(0.0, min(1.0, 1.0 - (diff_x ** (diff_x * 20))))
        wy = max(0.0, min(1.0, 1.0 - (diff_y ** (diff_y * 20))))

        def blend(est, meas, w):
            a = w
            b = 1.0 - w
            return (est*a + meas*b) / (a+b if a+b else 1.0)

        final_x = blend(pred_x, x0, wx)
        final_y = blend(pred_y, y0, wy)

        set_marker_position(tr, frame_now, final_x, final_y)

