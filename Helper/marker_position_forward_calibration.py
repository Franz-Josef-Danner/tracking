# Helper/marker_position_forward_calibration.py
from typing import Optional, Tuple, Dict, Any, Iterable
import ast
import bpy

# ---------------------------------------------------------------------
# Minimal-Logging + String-Handling + Key-Ermittlung (ohne Shift-Routine)
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
        _last_logged_values[key] = line


def _compare_tracks_with_scene(scene: bpy.types.Scene, key: str, names: Iterable[str]):
    """Vergleicht Tracknamen aus Scene-String mit realen Tracks des aktiven Clips; nur Info-Log bei Abweichung."""
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


def find_active_tracks_key(scene: bpy.types.Scene) -> Tuple[Optional[str], Dict[str, Any]]:
    """Ermittelt aktiven Key ('best_tracks' bevorzugt, sonst 'good_tracks') und liefert Meta-Infos."""
    meta = {
        'best': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
        'good': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
    }

    # BEST
    best_list, best_len = _read_scene_string(scene, "best_tracks")
    best_map, best_map_len = _read_scene_string(scene, "best_tracks_uuid_map")
    meta['best']['present']   = best_list is not None
    meta['best']['len']       = best_len
    meta['best']['has_uuid_map'] = best_map is not None
    meta['best']['map_len']   = best_map_len

    # GOOD
    good_list, good_len = _read_scene_string(scene, "good_tracks")
    good_map, good_map_len = _read_scene_string(scene, "good_tracks_uuid_map")
    meta['good']['present']   = good_list is not None
    meta['good']['len']       = good_len
    meta['good']['has_uuid_map'] = good_map is not None
    meta['good']['map_len']   = good_map_len

    # Optionales Logging (nur bei Änderung)
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

    # Aktiven Key bestimmen
    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"

    return active_key, meta


def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    key, _meta = find_active_tracks_key(scene)
    return key


# get_active_markers(frame) -> List[str|TrackObj]
# get_marker_position(track_or_name, frame) -> Tuple[float, float]
# set_marker_position(track_or_name, frame, x, y) -> None

# --- FEHLENDE IMPORTS HINZUGEFÜGT ---
from Helper.marker_positions_helper import (
    get_active_markers,
    get_marker_position,
    set_marker_position,
)


# ---------------------------------------------------------------------
# Marker-Korrektur über bis zu 4 Frames (adaptive Stabilisierung)
# Automatische Auswahl zwischen 'good_tracks' und 'best_tracks'
# ---------------------------------------------------------------------
def correct_marker_positions(
    scene: bpy.types.Scene,
    ref_tracks_input,
    calibrate_tracks,
    frame_now: int,
    frame_prev: Optional[int],
    frame_prev2: Optional[int] = None,
    frame_prev3: Optional[int] = None
):
    """
    Korrigierte Forward-Kalibrierung (symmetrisch zu Backward):
        frame_now  = aktueller Frame
        frame_prev = vergangener Frame (-1)
    """

    # -------------------------------------------------------------
    # Referenzen konsistent wie Backward auflösen
    # -------------------------------------------------------------
    if "best_tracks" in scene:
        ref_scene = _read_scene_list(scene, "best_tracks")
    elif "good_tracks" in scene:
        ref_scene = _read_scene_list(scene, "good_tracks")
    else:
        return

    if not ref_scene:
        return

    ref_tracks = list(set(ref_tracks_input) & set(ref_scene))
    if not ref_tracks:
        return

    # Mindestabdeckung
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    # Frames sauber spiegeln
    f0 = get_active_markers(frame_now)
    f1 = get_active_markers(frame_prev) if frame_prev else []
    f2 = get_active_markers(frame_prev2) if frame_prev2 else []
    f3 = get_active_markers(frame_prev3) if frame_prev3 else []

    f0_good = [m for m in f0 if m in ref_tracks]
    f1_good = [m for m in f1 if m in ref_tracks]
    f2_good = [m for m in f2 if m in ref_tracks]
    f3_good = [m for m in f3 if m in ref_tracks]

    # Auswahl identisch zu Backwards (4 → 3 → 2)
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

    # Aspect Ratio
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        w = clip.size[0]
        h = clip.size[1]
        aspect_ratio = w / h if h != 0 else 1.0
    except Exception:
        aspect_ratio = 1.0

    # -----------------------------------------------------------------
    # Marker-Korrekturen (vollständig gespiegelt)
    # -----------------------------------------------------------------
    for tr in calibrate_tracks:

        x_now,  y_now  = get_marker_position(tr, frame_now)
        x_prev, y_prev = get_marker_position(tr, frame_prev)

        vlist_x = []
        vlist_y = []

        for gm in source:
            g0x, g0y = get_marker_position(gm, frame_now)
            g1x, g1y = get_marker_position(gm, frame_prev)

            if mode >= 3:
                g2x, g2y = get_marker_position(gm, frame_prev2)
            if mode == 4:
                g3x, g3y = get_marker_position(gm, frame_prev3)

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

            dx = (x_now - g0x)
            dy = (y_now - g0y)
            dist = (dx*dx + dy*dy) ** 0.5
            w = 1.0 / (1e-6 + dist)

            vlist_x.append((vx, w))
            vlist_y.append((vy, w))

        if not vlist_x:
            continue

        def robust_weighted_mean(vw):
            if len(vw) < 5:
                sw = sum(w for _, w in vw)
                return sum(v*w for v, w in vw) / sw if sw else 0.0
            vs = sorted(vw, key=lambda x: x[0])
            n = len(vs)
            cut = max(1, int(0.1*n))
            trimmed = vs[cut:-cut] if n > 2*cut else vs
            sw = sum(w for _, w in trimmed)
            return sum(v*w for v, w in trimmed) / sw if sw else 0.0

        avg_vx = robust_weighted_mean(vlist_x)
        avg_vy = robust_weighted_mean(vlist_y)

        # Forward-Projektion (gespiegelt aus backward)
        pred_x = x_prev + avg_vx
        pred_y = y_prev + avg_vy

        diff_x = abs(x_now - pred_x)
        diff_y = abs(y_now - pred_y) * aspect_ratio

        wx = max(0.0, min(1.0, 1.0 - (diff_x ** (diff_x * 20))))
        wy = max(0.0, min(1.0, 1.0 - (diff_y ** (diff_y * 20))))

        def blend(est, meas, w):
            a = w
            b = 1.0 - w
            return (est*a + meas*b) / (a+b if (a+b) != 0 else 1.0)

        final_x = blend(pred_x, x_now, wx)
        final_y = blend(pred_y, y_now, wy)

        set_marker_position(tr, frame_now, final_x, final_y)

        # Optionales Debug-Log:


