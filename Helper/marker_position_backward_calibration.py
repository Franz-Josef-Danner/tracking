# Helper/marker_position_backward_calibration.py
# ------------------------------------------------------------
# Rückwärts-Tracking Marker-Kalibrierung
# Spiegelung der forward-Kalibrierung, aber mit umgedrehten
# Frames, Velocity-Richtung und adaptiver Blend-Logik.
# ------------------------------------------------------------

from typing import Optional, Tuple, Dict, Any, Iterable
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

def correct_marker_positions_backward(scene,
                                      calibrate_tracks,
                                      frame_now: int,
                                      frame_next: int,
                                      frame_next2: Optional[int] = None,
                                      frame_next3: Optional[int] = None):
    """
    Rückwärts-Kalibrierung:
    - frame_now  : aktueller Frame
    - frame_next : nächster Frame in Tracking-Richtung (also frame_now + 1)
    - weitere Frames optional
    """

    # ------------------------------------------------------------
    # Referenz-Trackliste bestimmen – identisch wie Forward
    # ------------------------------------------------------------
    ref_scene = None

    # Priorität: best_tracks → good_tracks
    if "best_tracks" in scene:
        ref_scene = _read_scene_list(scene, "best_tracks")
    elif "good_tracks" in scene:
        ref_scene = _read_scene_list(scene, "good_tracks")

    if not ref_scene:
        return

    # Nur existierende echte Tracks filtern
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        real_names = [t.name for t in clip.tracking.tracks]
        ref_scene = [t for t in ref_scene if t in real_names]
    except Exception:
        return

    if not ref_scene:
        return

    # Final verwendete Referenzliste
    good_refs = ref_scene

    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    # aktive Marker je Frame
    f0 = get_active_markers(frame_now)
    f1 = get_active_markers(frame_next)
    f2 = get_active_markers(frame_next2) if frame_next2 else []
    f3 = get_active_markers(frame_next3) if frame_next3 else []

    f0_good = [m for m in f0 if m in good_refs]
    f1_good = [m for m in f1 if m in good_refs]
    f2_good = [m for m in f2 if m in good_refs]
    f3_good = [m for m in f3 if m in good_refs]

    # Frame-Auswahl wie Forward, aber invertiert:
    if len(f3_good) >= min_required:
        source = f3_good
        mode = 4
    elif len(f2_good) >= min_required:
        source = f2_good
        mode = 3
    elif len(f1_good) >= min_required:
        source = f1_good
        mode = 2
    elif len(f0_good) >= min_required:
        return
    else:
        return

    # Clip-Aspect
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        width = clip.size[0]
        height = clip.size[1]
        aspect_ratio = width / height if height else 1.0
    except:
        aspect_ratio = 1.0

    # Korrektur
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

            # Velocity INVERTED for backward
            if mode == 4:
                vx = 0.5 * ((g2x - g3x) + (g1x - g2x))
                vy = 0.5 * ((g2y - g3y) + (g1y - g2y))
            elif mode == 3:
                vx = 0.5 * ((g2x - g1x) + (g1x - g0x))
                vy = 0.5 * ((g2y - g1y) + (g1y - g0y))
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

        if not wvx or not wvy:
            continue

        def robust_mean(vw):
            if len(vw) < 5:
                sw = sum(w for v, w in vw)
                return sum(v*w for v, w in vw) / sw if sw else 0.0
            vs = sorted(vw, key=lambda x: x[0])
            n = len(vs)
            cut = max(1, int(n*0.1))
            trimmed = vs[cut:-cut] if n > 2*cut else vs
            sw = sum(w for v, w in trimmed)
            return sum(v*w for v, w in trimmed) / sw if sw else 0.0

        avg_vx = robust_mean(wvx)
        avg_vy = robust_mean(wvy)

        # new pos predicted backward
        pred_x = x1 - avg_vx
        pred_y = y1 - avg_vy

        diff_x = abs(x0 - pred_x)
        diff_y = abs(y0 - pred_y) * aspect_ratio

        wx = max(0.0, min(1.0, 1.0 - (diff_x ** (diff_x * 20))))
        wy = max(0.0, min(1.0, 1.0 - (diff_y ** (diff_y * 20))))

        def blend(est, meas, w):
            a = w
            b = 1.0 - w
            num = est*a + meas*b
            den = a + b if (a+b)!=0 else 1.0
            return num/den

        final_x = blend(pred_x, x0, wx)
        final_y = blend(pred_y, y0, wy)

        set_marker_position(tr, frame_now, final_x, final_y)
