# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Szenen-String-Erkennung für "good_tracks" / "best_tracks" mit Logs
# + Ausgabe des neuen Strings "calibrate_tracks"
# Kompatibel mit UUID-Map-Varianten: "<key>" (List/String) und
# optional "<key>_uuid_map" (Dict-String {uuid: name})
# ---------------------------------------------------------------------

from typing import Optional, Tuple, Dict, Any
import ast
import bpy


def _read_scene_string(scene: bpy.types.Scene, key: str) -> Tuple[Optional[Any], int]:
    """
    Liest scene[key] und versucht – falls es ein String ist – eine
    strukturierte Form (list/dict) via ast.literal_eval herzustellen.
    Gibt zusätzlich die ermittelte Länge zurück (0 bei None / Fehler).
    """
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


def find_active_tracks_key(scene: bpy.types.Scene) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Prüft priorisiert auf 'best_tracks', danach auf 'good_tracks'.
    Loggt präzise, was gefunden wurde (inkl. Größen/Map-Status).
    Zusätzlich wird der Inhalt von 'calibrate_tracks' geloggt,
    falls vorhanden.
    """
    meta = {
        'best': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
        'good': {'present': False, 'len': 0, 'has_uuid_map': False, 'map_len': 0},
    }

    # --- BEST ---
    best_list, best_len = _read_scene_string(scene, "best_tracks")
    best_map, best_map_len = _read_scene_string(scene, "best_tracks_uuid_map")
    meta['best']['present'] = best_list is not None
    meta['best']['len'] = best_len
    meta['best']['has_uuid_map'] = best_map is not None
    meta['best']['map_len'] = best_map_len

    # --- GOOD ---
    good_list, good_len = _read_scene_string(scene, "good_tracks")
    good_map, good_map_len = _read_scene_string(scene, "good_tracks_uuid_map")
    meta['good']['present'] = good_list is not None
    meta['good']['len'] = good_len
    meta['good']['has_uuid_map'] = good_map is not None
    meta['good']['map_len'] = good_map_len

    # --- LOGGING ---
    print("[MarkerCalibration][SCAN] ---- Scene String Check ----")
    print(f"[MarkerCalibration][SCAN] best_tracks      present={meta['best']['present']} len={meta['best']['len']}")
    print(f"[MarkerCalibration][SCAN] best_tracks_uuid_map present={meta['best']['has_uuid_map']} len={meta['best']['map_len']}")
    print(f"[MarkerCalibration][SCAN] good_tracks      present={meta['good']['present']} len={meta['good']['len']}")
    print(f"[MarkerCalibration][SCAN] good_tracks_uuid_map present={meta['good']['has_uuid_map']} len={meta['good']['map_len']}")

    # --- CALIBRATE (NEU) ---
    calibrate_raw = scene.get("calibrate_tracks")
    if calibrate_raw is not None:
        try:
            if isinstance(calibrate_raw, str):
                try:
                    calibrate_eval = ast.literal_eval(calibrate_raw)
                except Exception:
                    # Kommagetrennt gespeichert -> in Liste umwandeln
                    calibrate_eval = calibrate_raw.split(",") if "," in calibrate_raw else [calibrate_raw]
            else:
                calibrate_eval = calibrate_raw

            if isinstance(calibrate_eval, (list, tuple, set)):
                preview = list(calibrate_eval)[:10]
                print(f"[MarkerCalibration][SCAN] calibrate_tracks present=True len={len(calibrate_eval)}")
                print(f"[MarkerCalibration][DATA] calibrate_tracks Beispiele ({len(calibrate_eval)}): {preview}")
            elif isinstance(calibrate_eval, dict):
                preview = list(calibrate_eval.keys())[:10]
                print(f"[MarkerCalibration][SCAN] calibrate_tracks present=True dict_keys={len(calibrate_eval)}")
                print(f"[MarkerCalibration][DATA] calibrate_tracks Dict-Keys: {preview}")
            else:
                print(f"[MarkerCalibration][SCAN] calibrate_tracks Typ={type(calibrate_eval).__name__} Inhalt={str(calibrate_eval)[:200]}")
        except Exception as e:
            print(f"[MarkerCalibration][DATA][ERROR] Konnte Inhalt von 'calibrate_tracks' nicht lesen: {e}")
    else:
        print("[MarkerCalibration][SCAN] calibrate_tracks present=False len=0")

    # --- SELECTION ---
    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
        print(f"[MarkerCalibration][SELECT] Aktiver Key: {active_key} | Items={meta['best']['len']} | UUID-Map={meta['best']['has_uuid_map']}({meta['best']['map_len']})")
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"
        print(f"[MarkerCalibration][SELECT] Aktiver Key: {active_key} | Items={meta['good']['len']} | UUID-Map={meta['good']['has_uuid_map']}({meta['good']['map_len']})")
    else:
        print("[MarkerCalibration][SELECT] Kein aktiver Key gefunden (weder 'best_tracks' noch 'good_tracks').")

    # --- Inhalt des aktiven Scene-Strings anzeigen ---
    if active_key:
        try:
            data_raw = scene.get(active_key)
            if isinstance(data_raw, str):
                try:
                    data_eval = ast.literal_eval(data_raw)
                except Exception:
                    data_eval = data_raw
            else:
                data_eval = data_raw

            if isinstance(data_eval, (list, tuple, set)):
                preview = list(data_eval)[:10]
                print(f"[MarkerCalibration][DATA] Beispiele ({len(data_eval)}): {preview}")
            elif isinstance(data_eval, dict):
                preview = list(data_eval.items())[:10]
                print(f"[MarkerCalibration][DATA] Dict-Keys ({len(data_eval)}): {[k for k, _ in preview]}")
            else:
                print(f"[MarkerCalibration][DATA] Typ={type(data_eval).__name__} | Inhalt={str(data_eval)[:200]}")
        except Exception as e:
            print(f"[MarkerCalibration][DATA][ERROR] Konnte Inhalt von '{active_key}' nicht lesen: {e}")

    return active_key, meta


def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    """
    Wrapper zur Ermittlung des aktiven Referenz-Keys mit Log.
    """
    key, _meta = find_active_tracks_key(scene)
    return key
