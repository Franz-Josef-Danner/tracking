# Helper/marker_position_forward_calibration.py
from typing import Optional, Tuple, Dict, Any, Iterable
import ast
import bpy

# ---------------------------------------------------------------------
# Minimal-Logging + Track-Vergleich zwischen Scene-Strings und Szene.
# ---------------------------------------------------------------------

_last_logged_values: Dict[str, str] = {}


def _read_scene_string(scene: bpy.types.Scene, key: str) -> Tuple[Optional[Any], int]:
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


def _log_if_changed(key: str, value: Any) -> None:
    content = _stringify_value_for_log(value).replace('"', "'")
    line = f"\"{key}\": \"{content}\""
    if _last_logged_values.get(key) != line:
        print(line)
        _last_logged_values[key] = line


# ---------------------------------------------------------------------
# Track-Vergleich (Existenzprüfung)
# ---------------------------------------------------------------------
def _compare_tracks_with_scene(scene: bpy.types.Scene, key: str, names: Iterable[str]):
    """Vergleicht die im String gespeicherten Tracknamen mit den realen Tracks des aktiven Clips."""
    if not names:
        return

    clip = None

    # 1️⃣ Versuche, aktiven Clip aus verschiedenen Quellen zu beziehen
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
        # Kein Clip verfügbar – Log-Ausgabe, kein Absturz
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

# ---------------------------------------------------------------------
# Kern-Funktion: Ermittlung aktiver Track-Strings
# ---------------------------------------------------------------------
def find_active_tracks_key(scene: bpy.types.Scene) -> Tuple[Optional[str], Dict[str, Any]]:
    meta = {
        'best': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
        'good': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
    }

    # BEST
    best_list, best_len = _read_scene_string(scene, "best_tracks")
    best_map, best_map_len = _read_scene_string(scene, "best_tracks_uuid_map")
    meta['best']['present'] = best_list is not None
    meta['best']['len'] = best_len
    meta['best']['has_uuid_map'] = best_map is not None
    meta['best']['map_len'] = best_map_len

    # GOOD
    good_list, good_len = _read_scene_string(scene, "good_tracks")
    good_map, good_map_len = _read_scene_string(scene, "good_tracks_uuid_map")
    meta['good']['present'] = good_list is not None
    meta['good']['len'] = good_len
    meta['good']['has_uuid_map'] = good_map is not None
    meta['good']['map_len'] = good_map_len

    # Logs nur bei Änderung
    calibrate_raw = scene.get("calibrate_tracks")
    if calibrate_raw is not None:
        try:
            if isinstance(calibrate_raw, str):
                try:
                    calibrate_eval = ast.literal_eval(calibrate_raw)
                except Exception:
                    calibrate_eval = calibrate_raw.split(",") if "," in calibrate_raw else [calibrate_raw]
            else:
                calibrate_eval = calibrate_raw
        except Exception:
            calibrate_eval = calibrate_raw
        _log_if_changed("calibrate_tracks", calibrate_eval)

    if best_list is not None:
        _log_if_changed("best_tracks", best_list)
        _compare_tracks_with_scene(scene, "best_tracks", best_list)
    if best_map is not None:
        _log_if_changed("best_tracks_uuid_map", best_map)
    if good_list is not None:
        _log_if_changed("good_tracks", good_list)
        _compare_tracks_with_scene(scene, "good_tracks", good_list)
    if good_map is not None:
        _log_if_changed("good_tracks_uuid_map", good_map)

    # Aktiven Key ermitteln
    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"

    return active_key, meta


def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    key, _meta = find_active_tracks_key(scene)
    return key


# ---------------------------------------------------------------------
# Korrektur-Algorithmus (unverändert)
# ---------------------------------------------------------------------
def correct_marker_positions(scene, good_trackss, selected_markers, frame_a, frame_b, frame_c=None, frame_d=None):
    if "good_tracks" in scene and "best_tracks" in scene:
        return
    elif "good_tracks" in scene:
        good_trackss = scene["good_tracks"]
    elif "best_tracks" in scene:
        good_trackss = scene["best_tracks"]
    else:
        return

    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    fa_marker = get_active_markers(frame_a)
    fb_marker = get_active_markers(frame_b)
    fc_marker = get_active_markers(frame_c) if frame_c else []
    fd_marker = get_active_markers(frame_d) if frame_d else []

    fa_good = [m for m in fa_marker if m in good_trackss]
    fb_good = [m for m in fb_marker if m in good_trackss]
    fc_good = [m for m in fc_marker if m in good_trackss]
    fd_good = [m for m in fd_marker if m in good_trackss]

    fa_gm_count, fb_gm_count = len(fa_good), len(fb_good)
    fc_gm_count, fd_gm_count = len(fc_good), len(fd_good)

    if fd_gm_count >= min_required:
        source, mode = fd_good, 4
    elif fc_gm_count >= min_required:
        source, mode = fc_good, 3
    elif fb_gm_count >= min_required:
        source, mode = fb_good, 2
    elif fa_gm_count >= min_required:
        return
    else:
        return

    def robust_weighted_mean(values_with_weights):
        if len(values_with_weights) < 5:
            total_w = sum(w for _, w in values_with_weights)
            return sum(v * w for v, w in values_with_weights) / total_w if total_w else 0.0
        sorted_vals = sorted(values_with_weights, key=lambda x: x[0])
        n = len(sorted_vals)
        cut = max(1, int(0.1 * n))
        trimmed = sorted_vals[cut:-cut] if n > 2 * cut else sorted_vals
        total_w = sum(w for _, w in trimmed)
        return sum(v * w for v, w in trimmed) / total_w if total_w else 0.0

    for sm in selected_markers:
        fa_sm_x, fa_sm_y = get_marker_position(sm, frame_a)
        fb_sm_x, fb_sm_y = get_marker_position(sm, frame_b)

        wvx, wvy = [], []
        for gm in source:
            fa_gm_x, fa_gm_y = get_marker_position(gm, frame_a)
            fb_gm_x, fb_gm_y = get_marker_position(gm, frame_b)
            if mode >= 3:
                fc_gm_x, fc_gm_y = get_marker_position(gm, frame_c)
            if mode == 4:
                fd_gm_x, fd_gm_y = get_marker_position(gm, frame_d)

            if mode == 4:
                v_gm_x = 0.5 * ((fb_gm_x - fc_gm_x) + (fa_gm_x - fb_gm_x))
                v_gm_y = 0.5 * ((fb_gm_y - fc_gm_y) + (fa_gm_y - fb_gm_y))
            elif mode == 3:
                v_gm_x = 0.5 * ((fb_gm_x - fc_gm_x) + (fa_gm_x - fb_gm_x))
                v_gm_y = 0.5 * ((fb_gm_y - fc_gm_y) + (fa_gm_y - fb_gm_y))
            elif mode == 2:
                v_gm_x = (fa_gm_x - fb_gm_x)
                v_gm_y = (fa_gm_y - fb_gm_y)
            else:
                v_gm_x = v_gm_y = 0.0

            dx, dy = (fa_sm_x - fa_gm_x), (fa_sm_y - fa_gm_y)
            dist = (dx * dx + dy * dy) ** 0.5
            w = 1.0 / (1e-6 + dist)
            wvx.append((v_gm_x, w))
            wvy.append((v_gm_y, w))

        if not wvx or not wvy:
            continue

        avg_vx = robust_weighted_mean(wvx)
        avg_vy = robust_weighted_mean(wvy)

        new_x = fb_sm_x + avg_vx
        new_y = fb_sm_y + avg_vy
        calib_x = 0.5 * (fa_sm_x + new_x)
        calib_y = 0.5 * (fa_sm_y + new_y)
        final_x = max(new_x * 0.95, min(new_x * 1.05, calib_x))
        final_y = max(new_y * 0.95, min(new_y * 1.05, calib_y))
        set_marker_position(sm, frame_a, final_x, final_y)
