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
        print(line)
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


# ---------------------------------------------------------------------
# Erwartete Low-Level-Helper (unverändert, extern bereitgestellt)
# ---------------------------------------------------------------------
# get_active_markers(frame) -> List[str|TrackObj]
# get_marker_position(track_or_name, frame) -> Tuple[float, float]
# set_marker_position(track_or_name, frame, x, y) -> None


# ---------------------------------------------------------------------
# Marker-Korrektur über bis zu 4 Frames (adaptive Stabilisierung)
# Automatische Auswahl zwischen 'good_tracks' und 'best_tracks'
# ---------------------------------------------------------------------
def correct_marker_positions(scene, good_trackss, calibrate_tracks, frame_a, frame_b, frame_c=None, frame_d=None):
    """
    Stabilisiert/rekonstruiert Markerpositionen im aktuellen Frame (frame_a)
    anhand „stabiler“ Marker-Referenzen aus bis zu vier Frames (frame_b…frame_d).
    Adaptive Gewichtung je nach Abweichung, robuste Mittelung, radiale Gewichte.
    """

    # Mutual Exclusivity & Auswahl der Referenzquelle
    if "good_tracks" in scene and "best_tracks" in scene:
        print("[Marker Correction] Fehler: Sowohl 'good_tracks' als auch 'best_tracks' existieren – Konflikt.")
        return
    elif "good_tracks" in scene:
        good_trackss = scene["good_tracks"]
        print("[Marker Correction] Verwende Marker-Set: 'good_tracks'")
    elif "best_tracks" in scene:
        good_trackss = scene["best_tracks"]
        print("[Marker Correction] Verwende Marker-Set: 'best_tracks'")
    else:
        print("[Marker Correction] Kein gültiger Marker-String ('good_tracks' oder 'best_tracks') vorhanden – Abbruch.")
        return

    # Mindestabdeckung
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    # Aktive Marker je Frame
    fa_marker = get_active_markers(frame_a)
    fb_marker = get_active_markers(frame_b)
    fc_marker = get_active_markers(frame_c) if frame_c else []
    fd_marker = get_active_markers(frame_d) if frame_d else []

    # Schnittmengen mit stabilen Referenzen
    fa_good = [m for m in fa_marker if m in good_trackss]
    fb_good = [m for m in fb_marker if m in good_trackss]
    fc_good = [m for m in fc_marker if m in good_trackss]
    fd_good = [m for m in fd_marker if m in good_trackss]

    fa_gm_count = len(fa_good)
    fb_gm_count = len(fb_good)
    fc_gm_count = len(fc_good)
    fd_gm_count = len(fd_good)

    # Fallauswahl 4→3→2→0
    if fd_gm_count >= min_required:
        source = fd_good
        mode = 4
    elif fc_gm_count >= min_required:
        source = fc_good
        mode = 3
    elif fb_gm_count >= min_required:
        source = fb_good
        mode = 2
    elif fa_gm_count >= min_required:
        print("[Marker Correction] Nur aktueller Frame – keine Korrektur notwendig.")
        return
    else:
        print("[Marker Correction] Zu wenige gültige Marker – Prozess abgebrochen.")
        print(f"[Marker Correction] Counts: a={fa_gm_count}, b={fb_gm_count}, c={fc_gm_count}, d={fd_gm_count}, required={min_required}")
        return

    # ----------------------------------------------------------
    # Auflösungs-Verhältnis für Y-Skalierung bestimmen
    # ----------------------------------------------------------
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        width = getattr(clip, "size", [1, 1])[0]
        height = getattr(clip, "size", [1, 1])[1]
        aspect_ratio = (width / height) if height != 0 else 1.0
    except Exception:
        aspect_ratio = 1.0

    # Positionsupdate für alle Zielmarker
    for sm in calibrate_tracks:
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

        def robust_weighted_mean(values_with_weights):
            if len(values_with_weights) < 5:
                total_w = sum(w for _, w in values_with_weights)
                return (sum(v * w for v, w in values_with_weights) / total_w) if total_w else 0.0
            sorted_vals = sorted(values_with_weights, key=lambda x: x[0])
            n = len(sorted_vals)
            cut = max(1, int(0.1 * n))
            trimmed = sorted_vals[cut:-cut] if n > 2 * cut else sorted_vals
            total_w = sum(w for _, w in trimmed)
            return (sum(v * w for v, w in trimmed) / total_w) if total_w else 0.0

        avg_vx = robust_weighted_mean(wvx)
        avg_vy = robust_weighted_mean(wvy)

        # ----------------------------------------------------------
        # Adaptive Stabilisierung (nichtlinear, quadratisch geglättet)
        # ----------------------------------------------------------
        new_x = fb_sm_x + avg_vx
        new_y = fb_sm_y + avg_vy

        # Abweichungen zwischen Schätzung und gemessener Markerposition
        diff_x = abs(fa_sm_x - new_x)
        diff_y = abs(fa_sm_y - new_y)

        # Seitenverhältnis berücksichtigen (aniso-Korrektur)
        w_aspect = aspect_ratio if aspect_ratio != 0 else 1.0
        diff_y *= w_aspect

        # Quadratische Gewichtsfunktion: (1 - diff²)
        wx_base = max(0.0, min(1.0, 1.0 - (diff_x * diff_x)))
        wy_base = max(0.0, min(1.0, 1.0 - (diff_y * diff_y)))

        # Normierte adaptive Mischung nach der exakten Formel:
        # ((S*(1-Δ²)) + (M*(1-(1-Δ²)))) / ((1-Δ²) + (1-(1-Δ²)))
        # vereinfacht zu gleitender, symmetrischer Blend
        def adaptive_blend(estimate, measure, w):
            a = w
            b = 1.0 - w
            numerator = (estimate * a) + (measure * b)
            denominator = a + b if (a + b) != 0 else 1.0
            return numerator / denominator

        final_x = adaptive_blend(new_x, fa_sm_x, wx_base)
        final_y = adaptive_blend(new_y, fa_sm_y, wy_base)

        set_marker_position(sm, frame_a, final_x, final_y)

        # Optionales Debug-Log:
        # print(f"[Adaptive] {sm}: Δx={diff_x:.4f}, Δy={diff_y:.4f}, wx={wx_base:.3f}, wy={wy_base:.3f}")

    print(f"[Marker Correction] Marker-Korrektur abgeschlossen – Basis: {mode}-Frame (robust, adaptiv, aspect={aspect_ratio:.3f}).")

