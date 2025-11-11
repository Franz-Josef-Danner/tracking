# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Szenen-String-Erkennung für "good_tracks" / "best_tracks" mit Logs
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
            # Fallback: Ungeparster String
            parsed = raw
    # Länge heuristisch bestimmen
    try:
        length = len(parsed)  # list/dict/tuple
    except Exception:
        length = 0
    return parsed, length


def find_active_tracks_key(scene: bpy.types.Scene) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Prüft priorisiert auf 'best_tracks', danach auf 'good_tracks'.
    Loggt präzise, was gefunden wurde (inkl. Größen/Map-Status).
    Rückgabe:
      - active_key: 'best_tracks' | 'good_tracks' | None
      - meta: {
          'best': {'present': bool, 'len': int, 'has_uuid_map': bool, 'map_len': int},
          'good': {'present': bool, 'len': int, 'has_uuid_map': bool, 'map_len': int}
        }
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

    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
        print(f"[MarkerCalibration][SELECT] Aktiver Key: {active_key} | Items={meta['best']['len']} | UUID-Map={meta['best']['has_uuid_map']}({meta['best']['map_len']})")
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"
        print(f"[MarkerCalibration][SELECT] Aktiver Key: {active_key} | Items={meta['good']['len']} | UUID-Map={meta['good']['has_uuid_map']}({meta['good']['map_len']})")
    else:
        print("[MarkerCalibration][SELECT] Kein aktiver Key gefunden (weder 'best_tracks' noch 'good_tracks').")

    return active_key, meta


# Beispiel: In Ihrer Korrekturfunktion aufrufen
def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    """
    Wrapper zur Ermittlung des aktiven Referenz-Keys mit Log.
    """
    key, _meta = find_active_tracks_key(scene)
    return key
