# Helper/detect.py — adaptive Merker-Detektion mit auflösungsbasierten Parametern,
#                    robustem Pre-Pass-Cleanup, UI-Kontext-Override, Handoff-Gate
#                    und Schutz vor Endlosschleifen.
#
# Wichtig (wie alte Operator-Version):
# - Handoff: handoff_to_pipeline=False  →  scene["detect_status"]="standalone_success",
#                                         scene["pipeline_do_not_start"]=True
#           handoff_to_pipeline=True   →  scene["detect_status"]="success",
#                                         scene["pipeline_do_not_start"]=False
#
# Kernpunkte:
# - Basen aus Auflösung: margin_base = width*0.025, min_distance_base = width*0.05
# - Skalierung: factor = log10(threshold*1e6)/6 → margin/min_distance
# - Threshold-Update (RUNNING): new = max(old * ((anzahl_neu + 0.1)/marker_adapt), 1e-4)
# - Cleanup: PRE-PASS (Zwischenstände/Persistenz), KEIN Short-Track-Clean
# - Zusatz-Airbag: __skip_clean_short_once / __just_created_names

import bpy
import math
from typing import Dict, Any, Optional, List, Tuple, Iterable
try:
    # optional, kann fehlen – wir kapseln Aufrufe defensiv
    from .naming import _safe_name as _naming_safe_name
except Exception:  # noqa: BLE001
    _naming_safe_name = None  # type: ignore[assignment]

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
    "detect_prepass_cleanup",
]

_LOCK_KEY = "__detect_lock"

# ---------------------------------------------------------------------------
# Kontext-Utilities & String/IDProperty-Sicherheit
# ---------------------------------------------------------------------------

def _coerce_utf8_str(x):
    """Ein Element robust nach str (UTF-8) bringen, fällt auf latin-1 zurück."""
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        try:
            return b.decode("utf-8").strip()
        except UnicodeDecodeError:
            try:
                return b.decode("latin-1").strip()
            except Exception:  # noqa: BLE001
                return None
    try:
        s = str(x).strip()
    except Exception:  # noqa: BLE001
        return None
    # mögliche Surrogates entschärfen
    s = s.replace("\udcff", "")
    return s or None


def _coerce_utf8_str_list(seq):
    return [s for s in (_coerce_utf8_str(x) for x in (seq or [])) if s]


def _ascii_safe(s: str) -> str:
    """Für Logs/IDProps – macht jeden String ASCII-sicher (\\u, \\x, \\N escapes)."""
    try:
        return s.encode("utf-8", "backslashreplace").decode("ascii", "backslashreplace")
    except Exception:  # noqa: BLE001
        return "<unprintable>"


def _debug_dump_names(label, seq):
    """ASCII-sicheres Logging, macht problematische Bytes sichtbar."""
    safe = []
    for x in (seq or []):
        if isinstance(x, (bytes, bytearray)):
            safe.append("BYTES(" + bytes(x).hex(" ") + ")")
        else:
            try:
                safe.append(_ascii_safe(str(x)))
            except Exception:  # noqa: BLE001
                safe.append(f"<unprintable type={type(x).__name__}>")
    print(f"[DetectDebug] {label}: {safe}")


def _safe_idprop_get_list(scn, key: str) -> List[str]:
    """
    Liest scene[key] defensiv. Wenn Blender/IDProperty beim Decoden crasht,
    wird die Property geleert und [] zurückgegeben.
    """
    try:
        raw = scn.get(key, [])
    except Exception as ex:  # noqa: BLE001
        print(f"[DetectDebug] IDProp READ FAIL scene[{key!r}] → {ex} | Reset auf []")
        try:
            scn[key] = []
        except Exception:  # noqa: BLE001
            pass
        return []
    # erfolgreiche Rückgabe – aber ggf. normalisieren
    return _coerce_utf8_str_list(raw if isinstance(raw, (list, tuple)) else [])


def _try_set_scene_list(scn, key: str, seq):
    """Setzt eine Stringliste robust in eine ID-Property; loggt, wenn’s kracht."""
    sanitized = _coerce_utf8_str_list(seq)
    # zusätzlich: erzwinge ASCII-safe Darstellung, damit Blender-UI/IDProps nie decoden müssen
    ascii_sanitized = [_ascii_safe(s) for s in sanitized]
    try:
        scn[key] = ascii_sanitized
    except Exception as ex:  # noqa: BLE001
        print(f"[DetectDebug] SANITIZE FAIL on set scene[{key!r}] → {ex}")
        _debug_dump_names(f"SANITIZE RAW {key}", seq)
        try:
            scn[key] = []
        except Exception:  # noqa: BLE001
            pass


def _find_clip_editor_context():
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return window, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    window, area, region, space = _find_clip_editor_context()
    if not (window and area and region and space):
        raise RuntimeError("No CLIP_EDITOR context available for operator.")
    override = {
        "window": window,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


# ---------------------------------------------------------------------------
# Daten-Utilities
# ---------------------------------------------------------------------------

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


def _remove_tracks_by_name(tracking: bpy.types.MovieTracking, names_to_remove: Iterable[str]) -> int:
    if not names_to_remove:
        return 0
    removed = 0
    target = set(_coerce_utf8_str_list(names_to_remove))
    for t in list(tracking.tracks):
        if _coerce_utf8_str(t.name) in target:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:  # noqa: BLE001
                pass
    return removed


def _collect_existing_positions(
    tracking: bpy.types.MovieTracking, frame: int, w: int, h: int
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for t in tracking.tracks:
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0] * w, m.co[1] * h))
    return out


def _resolve_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == "CLIP_EDITOR":
        c = getattr(space, "clip", None)
        if c:
            return c
    for c in bpy.data.movieclips:
        return c
    return None


def _scaled_params(
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> Tuple[int, int]:
    factor = math.log10(max(float(threshold), 1e-6) * 1e6) / 6.0
    margin = max(1, int(int(margin_base) * factor))
    min_distance = max(1, int(int(min_distance_base) * factor))
    return margin, min_distance


def _safe_track_name(track: bpy.types.MovieTrackingTrack) -> Optional[str]:
    """
    Liefert einen robusten, für IDProps geeigneten Namen.
    Versucht zuerst .naming._safe_name (falls vorhanden), sonst Sanitizing.
    """
    # 1) versuche naming._safe_name defensiv
    if _naming_safe_name:
        try:
            n = _naming_safe_name(track)
            if n:
                n = str(n).strip()
                if n:
                    return _ascii_safe(n)
        except Exception:  # noqa: BLE001
            pass

    # 2) direkten Namen sicher verwerten
    raw = getattr(track, "name", None)
    if isinstance(raw, (bytes, bytearray)):
        b = bytes(raw)
        for enc in ("utf-8", "latin-1"):
            try:
                s = b.decode(enc).strip()
                if s:
                    return _ascii_safe(s)
            except Exception:  # noqa: BLE001
                continue
        # letzte Eskalationsstufe: Hex
        return f"BYTES({b.hex()})"
    try:
        s = str(raw).strip() if raw is not None else None
    except Exception:  # noqa: BLE001
        s = None
    if s:
        return _ascii_safe(s)
    return None


# ---------------------------------------------------------------------------
# PRE-PASS (Zwischenstände/Persistenz bereinigen, KEIN Short-Track-Clean)
# ---------------------------------------------------------------------------
def detect_prepass_cleanup(context, *, remove_names=None):
    """Bereinigt Persistenz/Zwischenstände für Detect-Retries UND löscht
    die im letzten Run erzeugten Tracks (Legacy-Verhalten)."""
    scn = context.scene

    # 1) Namen aus letztem erfolgreichen Detect defensiv lesen
    prev_raw = _safe_idprop_get_list(scn, "detect_prev_names")
    if prev_raw:
        _debug_dump_names("Prev RAW (pre-sanitize)", prev_raw)

    # 2) Zielmenge zusammenstellen: prev_names (+ optional remove_names)
    names_to_remove = set(_coerce_utf8_str_list(prev_raw))
    if remove_names:
        names_to_remove.update(_coerce_utf8_str_list(remove_names))

    # 3) Tracks jetzt wirklich löschen (wie im alten Operator)
    clip = _resolve_clip(context)
    if clip and names_to_remove:
        _remove_tracks_by_name(clip.tracking, names_to_remove)

    # 4) Liste leeren (sauberer Zustand für den nächsten Run)
    try:
        scn["detect_prev_names"] = []
    except Exception:
        pass

    # 5) Frischliste normalisieren (CleanShort nutzt sie als Schutz)
    fresh_raw = _safe_idprop_get_list(scn, "__just_created_names")
    if fresh_raw:
        _try_set_scene_list(scn, "__just_created_names", fresh_raw)  # garantiert ASCII-safe


def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    margin, min_distance = _scaled_params(
        float(threshold),
        int(margin_base),
        int(min_distance_base),
    )
    try:
        _run_in_clip_context(
            lambda **kw: bpy.ops.clip.detect_features(**kw),
            margin=margin,
            min_distance=min_distance,
            threshold=float(threshold),
        )
    except Exception as ex:  # noqa: BLE001
        print("[DetectDebug] detect_features failed in override:", ex)
        raise
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------------
# EIN einzelner Detect-Pass
# ---------------------------------------------------------------------------

def run_detect_once(
    context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    marker_adapt: Optional[int] = None,
    min_marker: Optional[int] = None,
    max_marker: Optional[int] = None,
    margin_base: Optional[int] = None,        # px; Default = 2.5% Bildbreite
    min_distance_base: Optional[int] = None,  # px; Default = 5% Bildbreite
    close_dist_rel: float = 0.01,             # 1% Bildbreite
    handoff_to_pipeline: bool = False,        # Gate wie alte Version
) -> Dict[str, Any]:
    """
    Rückgabe: {"status": "READY" | "RUNNING" | "FAILED",
               "new_tracks": int, "threshold": float, "frame": int,
               "created_names": list[str]}
    """
    scn = context.scene
    scn[_LOCK_KEY] = True

    try:
        clip = _resolve_clip(context)
        if not clip:
            return {"status": "FAILED", "reason": "no_clip"}

        tracking = clip.tracking
        settings = tracking.settings
        width, height = int(clip.size[0]), int(clip.size[1])

        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:  # noqa: BLE001
                pass
        frame = int(scn.frame_current)

        # PRE-PASS Cleanup (Zwischenstände aus vorherigen RUNNING-Durchläufen)
        detect_prepass_cleanup(context)

        # Threshold laden
        if threshold is None:
            base_thr = float(getattr(settings, "default_correlation_min", 0.75))
            try:
                last_thr = float(scn.get("last_detection_threshold", base_thr))
            except Exception:  # noqa: BLE001
                last_thr = base_thr
            threshold = max(1e-6, float(last_thr))
        else:
            threshold = max(1e-6, float(threshold))

        # Zielkorridor
        if marker_adapt is None:
            try:
                marker_adapt = int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
            except Exception:  # noqa: BLE001
                marker_adapt = int(scn.get("marker_basis", 20))
        safe_adapt = max(1, int(marker_adapt))

        if min_marker is None:
            min_marker = int(max(1, round(safe_adapt * 0.9)))
        if max_marker is None:
            max_marker = int(max(2, round(safe_adapt * 1.2)))

        # Auflösungsbasen
        if margin_base is None:
            margin_base = max(1, int(width * 0.025))
        if min_distance_base is None:
            min_distance_base = max(1, int(width * 0.05))

        # Snapshot
        initial_names = {_coerce_utf8_str(t.name) or str(t.name) for t in tracking.tracks}
        existing_px = _collect_existing_positions(tracking, frame, width, height)

        # Detect
        _deselect_all(tracking)
        try:
            perform_marker_detection(
                clip, tracking,
                float(threshold),
                int(margin_base), int(min_distance_base),
            )
        except Exception as ex:  # noqa: BLE001
            print("[DetectDebug] FAILED: Operator bpy.ops.clip.detect_features failed:", ex)
            try:
                scn["detect_status"] = "failed"
            except Exception:  # noqa: BLE001
                pass
            return {"status": "FAILED", "reason": "detect_features_failed"}

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:  # noqa: BLE001
            pass

        # Neue Tracks
        tracks = tracking.tracks
        new_tracks_raw = [t for t in tracks if (_coerce_utf8_str(t.name) or str(t.name)) not in initial_names]
        added_names = {_coerce_utf8_str(t.name) or str(t.name) for t in new_tracks_raw}

        # Near-Duplicates entfernen
        rel = close_dist_rel if close_dist_rel > 0.0 else 0.01
        distance_px = max(1, int(width * rel))
        thr2 = float(distance_px * distance_px)

        close_tracks: List[bpy.types.MovieTrackingTrack] = []
        if existing_px and new_tracks_raw:
            for tr in new_tracks_raw:
                try:
                    m = tr.markers.find_frame(frame, exact=True)
                except TypeError:
                    m = tr.markers.find_frame(frame)
                if m and not getattr(m, "mute", False):
                    x = m.co[0] * width
                    y = m.co[1] * height
                    for ex, ey in existing_px:
                        dx = x - ex
                        dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(tr)
                            break

        if close_tracks:
            _deselect_all(tracking)
            for t in close_tracks:
                t.select = True
            try:
                _run_in_clip_context(lambda **kw: bpy.ops.clip.delete_track(**kw))
            except Exception:  # noqa: BLE001
                _remove_tracks_by_name(tracking, {t.name for t in close_tracks})

        close_set = {t.name for t in close_tracks}
        cleaned_tracks = [t for t in new_tracks_raw if t.name not in close_set]
        anzahl_neu = len(cleaned_tracks)

        created_names: List[str] = []
        for t in cleaned_tracks:
            n = _safe_track_name(t)
            if n:
                n = n.strip()
                if n:
                    created_names.append(n)

        print(
            "[DetectDebug] Frame=%d | anzahl_neu=%d | marker_min=%d | marker_max=%d | "
            "marker_adapt=%d | threshold_old=%.6f"
            % (frame, anzahl_neu, int(min_marker), int(max_marker), int(marker_adapt), float(threshold))
        )

        # Korridorprüfung
        if anzahl_neu < int(min_marker) or anzahl_neu > int(max_marker):
            remaining_after_delete: List[str] = []

            if added_names:
                _deselect_all(tracking)
                for t in tracks:
                    if (_coerce_utf8_str(t.name) or str(t.name)) in added_names:
                        t.select = True
                try:
                    _run_in_clip_context(lambda **kw: bpy.ops.clip.delete_track(**kw))
                except Exception:  # noqa: BLE001
                    pass

                still_there = [(_coerce_utf8_str(t.name) or str(t.name)) for t in tracking.tracks
                               if (_coerce_utf8_str(t.name) or str(t.name)) in added_names]
                if still_there:
                    _remove_tracks_by_name(tracking, still_there)
                    remaining = [(_coerce_utf8_str(t.name) or str(t.name)) for t in tracking.tracks
                                 if (_coerce_utf8_str(t.name) or str(t.name)) in added_names]
                    remaining_after_delete = remaining or []
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:  # noqa: BLE001
                    pass

            # Sanitize & optional Diagnoselog
            if remaining_after_delete:
                _debug_dump_names("Remaining RAW (pre-sanitize)", remaining_after_delete)

            new_threshold = max(
                float(threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            try:
                scn["last_detection_threshold"] = float(new_threshold)
                scn["detect_status"] = "running"  # Detect wird erneut versucht
                _try_set_scene_list(scn, "detect_prev_names", remaining_after_delete)
            except Exception:  # noqa: BLE001
                pass

            print(
                "[DetectDebug] RUNNING → new_threshold=%.6f (old=%.6f, adapt=%d) | anzahl_neu=%d | corridor=[%d..%d]"
                % (float(new_threshold), float(threshold), int(marker_adapt),
                   int(anzahl_neu), int(min_marker), int(max_marker))
            )

            return {
                "status": "RUNNING",
                "new_tracks": int(anzahl_neu),
                "threshold": float(new_threshold),
                "frame": int(frame),
                "created_names": created_names,
            }

        # READY: Erfolg  (→ wie alte Version: erzeugte Namen für nächsten Run merken)
        try:
            _try_set_scene_list(scn, "detect_prev_names", created_names)
            scn["last_detection_threshold"] = float(threshold)
        except Exception:  # noqa: BLE001
            pass

        # === Handoff-Gate ===
        try:
            if handoff_to_pipeline:
                scn["detect_status"] = "success"
                scn["pipeline_do_not_start"] = False
            else:
                scn["detect_status"] = "standalone_success"
                scn["pipeline_do_not_start"] = True
        except Exception:  # noqa: BLE001
            pass
        # ====================

        # Airbag gegen CleanShort direkt danach
        try:
            scn["__skip_clean_short_once"] = True
            _try_set_scene_list(scn, "__just_created_names", created_names)
        except Exception:  # noqa: BLE001
            pass

        print(
            "[DetectDebug] READY | anzahl_neu=%d liegt im Korridor [%d..%d] | threshold_keep=%.6f | created=%d"
            % (int(anzahl_neu), int(min_marker), int(max_marker), float(threshold), len(created_names))
        )

        return {
            "status": "READY",
            "new_tracks": int(anzahl_neu),
            "threshold": float(threshold),
            "frame": int(frame),
            "created_names": created_names,
        }

    except Exception as ex:  # noqa: BLE001
        print("[DetectDebug] FAILED:", ex)
        try:
            scn["detect_status"] = "failed"
        except Exception:  # noqa: BLE001
            pass
        return {"status": "FAILED", "reason": str(ex)}
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Optionaler Mehrfach-Wrapper
# ---------------------------------------------------------------------------

def run_detect_adaptive(
    context,
    *,
    start_frame: Optional[int] = None,
    max_attempts: int = 8,
    **kwargs,
) -> Dict[str, Any]:
    last: Dict[str, Any] = {}
    for _ in range(max_attempts):
        last = run_detect_once(context, start_frame=start_frame, **kwargs)
        if last.get("status") in ("READY", "FAILED"):
            return last
        start_frame = last.get("frame", start_frame)
    return last or {"status": "FAILED", "reason": "max_attempts_exceeded"}
