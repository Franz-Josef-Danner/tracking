# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Marker-Korrektur + Vergleich zwischen Scene-Strings und realen Tracks
# ---------------------------------------------------------------------

from typing import Optional, Tuple, Dict, Any, Iterable, List
import ast
import bpy

_last_logged_values: Dict[str, str] = {}


# ============================================================
# Scene-String Handling
# ============================================================

def _read_scene_string(scene: bpy.types.Scene, key: str) -> Tuple[Optional[Any], int]:
    raw = scene.get(key)
    if raw is None:
        return None, 0
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            parsed = raw.split(",") if "," in raw else [raw]
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
        return str(value).replace("\n", " ").replace("\r", " ")
    except Exception:
        return str(value)


def _log_if_changed(key: str, value: Any) -> None:
    content = _stringify_value_for_log(value).replace('"', "'")
    line = f"\"{key}\": \"{content}\""
    if _last_logged_values.get(key) != line:
        print(line)
        _last_logged_values[key] = line


# ============================================================
# Vergleich zwischen Scene-String und realen Tracks
# ============================================================

def _compare_scene_tracks(scene: bpy.types.Scene, key: str, names: Iterable[str]) -> None:
    """Vergleicht Tracks aus Scene-String mit den tatsächlich im Clip vorhandenen."""
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        if not clip or not clip.tracking:
            print(f"[COMPARE][{key}] ❌ Kein aktiver Clip gefunden.")
            return
        scene_tracks = {t.name for t in clip.tracking.tracks}
        ref_tracks = set(map(str, names))
        found = sorted(scene_tracks.intersection(ref_tracks))
        missing = sorted(ref_tracks - scene_tracks)
        extra = sorted(scene_tracks - ref_tracks)
        print(f"[COMPARE][{key}] 🎞️ Szene enthält {len(scene_tracks)} Tracks.")
        print(f"[COMPARE][{key}] ✅ Übereinstimmungen: {len(found)}")
        print(f"[COMPARE][{key}] ❌ Fehlend in Szene: {len(missing)} → {missing[:10]}")
        print(f"[COMPARE][{key}] ⚠️ Extra in Szene (nicht im String): {len(extra)} → {extra[:10]}")
    except Exception as e:
        print(f"[COMPARE][{key}] ❌ Fehler beim Vergleich: {e}")


# ============================================================
# Bestimmung aktiver Referenzstrings + Logging
# ============================================================

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

    # CALIBRATE
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
        _compare_scene_tracks(scene, "calibrate_tracks", calibrate_eval)

    # Logs & Vergleiche
    if best_list is not None:
        _log_if_changed("best_tracks", best_list)
        _compare_scene_tracks(scene, "best_tracks", best_list)
    if best_map is not None:
        _log_if_changed("best_tracks_uuid_map", best_map)
    if good_list is not None:
        _log_if_changed("good_tracks", good_list)
        _compare_scene_tracks(scene, "good_tracks", good_list)
    if good_map is not None:
        _log_if_changed("good_tracks_uuid_map", good_map)

    # Aktiven Key bestimmen
    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"

    print(f"[COMPARE] 🔍 Aktiver Key: {active_key or 'None'} | Items={meta.get(active_key.split('_')[0],{}).get('len',0)}")
    return active_key, meta


# ============================================================
# Platzhalter für deine bestehenden Low-Level Markerfunktionen
# ============================================================

def get_active_markers(frame: int) -> List[str]:
    """Dummy – Platzhalter für dein bestehendes System"""
    return []


def get_marker_position(marker, frame: int) -> Tuple[float, float]:
    """Dummy – Platzhalter"""
    return (0.0, 0.0)


def set_marker_position(marker, frame: int, x: float, y: float):
    """Dummy – Platzhalter"""
    pass


# ============================================================
# Marker-Korrektur
# ============================================================

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

    # ... Rest deines bestehenden Algorithmus unverändert ...
