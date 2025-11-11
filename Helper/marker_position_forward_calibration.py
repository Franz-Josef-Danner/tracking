# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Minimal-Logging: Ausgabe nur bei Änderung im Format
# "<String Name>": "<Inhalt>"
# ---------------------------------------------------------------------

from typing import Optional, Tuple, Dict, Any, Iterable
import ast
import bpy

# Modulweiter Cache für zuletzt geloggte Inhalte
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
    """
    Serialisiert den Wert kompakt für die Ein-Zeilen-Logausgabe.
    - Sequenzen (list/tuple/set): kommagetrennt in einer Zeile
    - Dict: Keys kommagetrennt (stabil sortiert)
    - Sonst: str(value)
    Resultat ist eine reine Zeichenkette ohne Zeilenumbrüche.
    """
    try:
        if isinstance(value, dict):
            try:
                keys = sorted(list(value.keys()))
            except Exception:
                keys = list(value.keys())
            return ",".join(str(k) for k in keys)
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(x) for x in value)
        # Fallback: einfache String-Repräsentation
        s = str(value)
        return s.replace("\n", " ").replace("\r", " ")
    except Exception:
        # Defensive Fallback
        return str(value)


def _log_if_changed(key: str, value: Any) -> None:
    """
    Loggt exakt eine Zeile im Format:
    "<key>": "<content>"
    aber nur, wenn sich der serialisierte Inhalt gegenüber der letzten Ausgabe geändert hat.
    """
    content = _stringify_value_for_log(value)
    # Stabilisiere Anführungszeichen im Inhalt
    safe_content = content.replace('"', "'")
    line = f"\"{key}\": \"{safe_content}\""

    prev = _last_logged_values.get(key)
    if prev != line:
        print(line)
        _last_logged_values[key] = line
    # Wenn gleich, keine Ausgabe


def find_active_tracks_key(scene: bpy.types.Scene) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Liefert wie bisher den aktiven Referenz-Key ('best_tracks'/'good_tracks'/None)
    und Meta-Daten zurück. Logging ist auf Minimal-Variante reduziert:
    - Es wird ausschließlich 'calibrate_tracks' geloggt (nur bei Änderung),
      im Format "<String Name>": "<Inhalt>".
    """
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

    # --- EINZIGES LOG-ZIEL: calibrate_tracks (nur bei Änderung) ---
    calibrate_raw = scene.get("calibrate_tracks")
    if calibrate_raw is not None:
        # Falls als String gespeichert: eval oder split(",")
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

    # --- Auswahl des aktiven Referenz-Keys (ohne Log) ---
    active_key = None
    if meta['best']['present'] and meta['best']['len'] > 0:
        active_key = "best_tracks"
    elif meta['good']['present'] and meta['good']['len'] > 0:
        active_key = "good_tracks"

    return active_key, meta


def _resolve_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    key, _meta = find_active_tracks_key(scene)
    return key
