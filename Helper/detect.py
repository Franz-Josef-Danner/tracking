# Helper/detect.py — vollständige, robuste Detect-Implementierung
#
# Ziele:
# - Vor jedem Detect: alte (vom letzten Detect erzeugte) Tracks entfernen
# - Namens-/Encoding-Probleme vermeiden (NBSP, Latin-1-Fallback, Unicode-Normalisierung)
# - Nach Detect: neu entstandene Tracks erfassen und in Scene-Property ablegen
# - Sichere Rückgabewerte für die Orchestrator-Pipeline
#
# Kompatibel mit Blender 4.x. PEP 8-konform, defensives Error-Handling.

from __future__ import annotations

import unicodedata
from typing import Iterable, List, Set, Dict
import bpy

# Scene-Keys
DETECT_PREV_KEY = "detect_prev_names"            # list[str] – zuletzt erzeugte Tracks
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float – zuletzt verwendete Schwelle


# ------------------------------------------------------------
# Utilities: Encoding-/Namenshygiene
# ------------------------------------------------------------

def _safe_str(x) -> str:
    """Robustes String-Coercion mit Unicode-Normalisierung.
    - Bytes werden bevorzugt als UTF-8, sonst Latin-1 dekodiert
    - NBSP (\u00A0) → normales Space
    - NFKC-Normalisierung, trim
    """
    if isinstance(x, (bytes, bytearray)):
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                x = x.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            x = x.decode("latin-1", errors="replace")
    s = str(x).replace("\u00A0", " ")
    return unicodedata.normalize("NFKC", s).strip()


def _ascii_safe_name(s: str) -> str:
    """Reduziert auf ASCII-gültige ID-Property-kompatible Namen.
    Nützlich, um Scene-Listen sicher abzulegen.
    """
    s = _safe_str(s)
    try:
        ascii_bytes = s.encode("ascii", errors="ignore")
        s_ascii = ascii_bytes.decode("ascii")
    except Exception:
        s_ascii = s
    s_ascii = s_ascii.strip()
    if not s_ascii:
        s_ascii = "Track"
    return s_ascii


def _log_detect(msg: str) -> None:
    print(f"[DetectDebug] {msg}")


# ------------------------------------------------------------
# Zugriff auf Clip/Tracks
# ------------------------------------------------------------

def _get_movieclip(context: bpy.types.Context):
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    return mc


def _iter_tracks(mc) -> Iterable[bpy.types.MovieTrackingTrack]:
    try:
        return list(mc.tracking.tracks)
    except Exception:
        return []


def _list_track_names(mc) -> List[str]:
    names: List[str] = []
    for tr in _iter_tracks(mc):
        try:
            names.append(_safe_str(tr.name))
        except Exception:
            names.append("?")
    return names


# ------------------------------------------------------------
# Scene-Listen robust speichern/lesen
# ------------------------------------------------------------

def _get_scene_list(scene: bpy.types.Scene, key: str) -> List[str]:
    try:
        raw = scene.get(key, [])
        if isinstance(raw, (list, tuple)):
            return [_safe_str(x) for x in raw]
        if isinstance(raw, str):  # falls versehentlich CSV
            return [_safe_str(x) for x in raw.split("|") if x]
        return []
    except Exception:
        return []


def _set_scene_list(scene: bpy.types.Scene, key: str, values: Iterable[str]) -> None:
    try:
        cleaned = [_ascii_safe_name(v) for v in values]
        scene[key] = cleaned
    except Exception:
        # Fallback: CSV im String
        try:
            scene[key] = "|".join(_ascii_safe_name(v) for v in values)
        except Exception:
            pass


# ------------------------------------------------------------
# Pre-Pass: Alte Detect-Tracks sicher entfernen
# ------------------------------------------------------------

def detect_prepass_cleanup(context: bpy.types.Context) -> Dict[str, int | str]:
    mc = _get_movieclip(context)
    if not mc:
        return {"status": "FAILED", "reason": "no_movieclip"}

    prev_names = set(_get_scene_list(context.scene, DETECT_PREV_KEY))
    if not prev_names:
        return {"status": "EMPTY"}

    # Entfernen nach Name (defensiv)
    tracks = list(mc.tracking.tracks)
    removed = 0
    for tr in tracks:
        try:
            name = _safe_str(tr.name)
            if name in prev_names or _ascii_safe_name(name) in prev_names:
                try:
                    mc.tracking.tracks.remove(tr)
                    removed += 1
                except Exception:
                    pass
        except Exception:
            pass

    _set_scene_list(context.scene, DETECT_PREV_KEY, [])
    _log_detect(f"Pre-Cleanup: removed={removed} from prev_names={len(prev_names)}")
    return {"status": "OK", "removed": removed}


# ------------------------------------------------------------
# Detect: Kernfunktion
# ------------------------------------------------------------

def _frame_set(context: bpy.types.Context, frame: int) -> None:
    try:
        context.scene.frame_set(int(frame), subframe=0.0)
    except Exception:
        pass


def _call_blender_detect(threshold: float | None = None) -> bool:
    """Ruft Blender's detect_features Operator defensiv auf.
    Die Signatur kann zwischen Versionen leicht variieren; wir probieren minimal und mit Schwelle.
    """
    # Minimaler Call
    try:
        if threshold is None:
            bpy.ops.clip.detect_features("EXEC_DEFAULT")
            return True
        # Versuch mit Threshold-Argument
        try:
            bpy.ops.clip.detect_features("EXEC_DEFAULT", threshold=float(threshold))
            return True
        except TypeError:
            # Fallback: einige Builds nutzen 'placement'/'margin' etc. – wir ignoren optional args
            bpy.ops.clip.detect_features("EXEC_DEFAULT")
            return True
    except Exception:
        return False


def run_detect_once(context: bpy.types.Context, start_frame: int, handoff_to_pipeline: bool = True) -> Dict[str, object]:
    """Führt einmalig die Marker-Detection aus.

    Returns
    -------
    dict
        { 'status': 'READY'|'RUNNING'|'FAILED', 'created': int, 'frame': int, 'reason': str? }
    """
    mc = _get_movieclip(context)
    if not mc:
        return {"status": "FAILED", "reason": "no_movieclip"}

    # 1) Pre-Cleanup der letzten Detect-Charge
    cleanup_info = detect_prepass_cleanup(context)
    # 2) Frame setzen
    _frame_set(context, start_frame)

    # 3) Vorher-Status erfassen
    prev_raw = _list_track_names(mc)
    _log_detect(f"Prev RAW (pre-sanitize): {prev_raw}")

    prev_set: Set[str] = set(_ascii_safe_name(n) for n in prev_raw)

    # 4) Schwelle bestimmen
    try:
        thr = float(context.scene.get(DETECT_LAST_THRESHOLD_KEY, 0.005))
    except Exception:
        thr = 0.005

    # 5) Detect ausführen (Blender-Operator)
    ok = _call_blender_detect(threshold=thr)
    if not ok:
        return {"status": "FAILED", "reason": "detect_features_op_failed"}

    # 6) Nachher-Status erfassen
    after_raw = _list_track_names(mc)
    after_set: Set[str] = set(_ascii_safe_name(n) for n in after_raw)

    created_names = sorted(after_set - prev_set)
    created_count = len(created_names)

    # 7) Ergebnis protokollieren und für nächsten Run speichern
    _set_scene_list(context.scene, DETECT_PREV_KEY, created_names)
    try:
        context.scene[DETECT_LAST_THRESHOLD_KEY] = float(thr)
    except Exception:
        pass

    # Heuristik/Feedback: Im echten Projekt gibt es ggf. Korridorprüfung (min/max). Hier nur Info.
    _log_detect(
        f"Frame={start_frame} | created={created_count} | threshold_keep={thr} | cleanup={cleanup_info.get('removed', 0)}"
    )

    return {"status": "READY", "created": created_count, "frame": int(start_frame)}
