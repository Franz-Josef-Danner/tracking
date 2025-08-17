# Helper/detect.py — adaptive Marker-Detektion mit selektionsbasiertem Pre-Pass-Cleanup,
# UI-Kontext-Override, Encoding-Sanitizing, Handoff-Gates und Schutz vor Endlosschleifen.
#
# Exportierte API:
#   - perform_marker_detection(...)
#   - run_detect_once(...)
#   - run_detect_adaptive(...)
#   - detect_prepass_cleanup(...)
#
# Verhalten:
# - Vor jedem Detect werden die vom letzten Detect erzeugten Tracks per Selektion gelöscht
#   (Tracks sind getaggt mit track["__detect_created"] == True).
# - Near-Duplicates werden per Selektion entfernt.
# - Korridorprüfung steuert adaptive Threshold-Anpassung (Status "RUNNING") für erneute Versuche.
# - Handoff: handoff_to_pipeline steuert detect_status + pipeline_do_not_start.
# - Alle String-/IDProperty-Zugriffe sind encoding-sicher (UTF-8 → Latin-1 Fallback, ASCII-safe Ablage).

from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import bpy

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
    "detect_prepass_cleanup",
]

# Scene-Keys
DETECT_PREV_KEY = "detect_prev_names"                   # list[str] – legacy, wird geleert
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float – zuletzt verwendete Schwelle
_LOCK_KEY = "__detect_lock"

# ============================================================
# Encoding-/Namenshygiene & IDProperty-Utilities
# ============================================================

def _safe_str(x) -> str:
    """Robustes String-Coercion (UTF-8 bevorzugt, Latin-1 Fallback) + NBSP -> Space + NFKC."""
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                x = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            x = b.decode("latin-1", errors="replace")
    s = str(x).replace("\u00A0", " ")
    return unicodedata.normalize("NFKC", s).strip()


def _coerce_utf8_str(x) -> Optional[str]:
    try:
        s = _safe_str(x)
        return s if s else None
    except Exception:
        return None


def _coerce_utf8_str_list(seq) -> List[str]:
    return [s for s in (_coerce_utf8_str(x) for x in (seq or [])) if s]


def _ascii_safe(s: str) -> str:
    try:
        return s.encode("utf-8", "backslashreplace").decode("ascii", "backslashreplace")
    except Exception:
        return "<unprintable>"


def _try_set_scene_list(scn: bpy.types.Scene, key: str, seq) -> None:
    sanitized = _coerce_utf8_str_list(seq)
    ascii_sanitized = [_ascii_safe(s) for s in sanitized]
    try:
        scn[key] = ascii_sanitized
    except Exception as ex:
        print(f"[DetectDebug] SANITIZE FAIL on set scene[{key!r}] → {ex}")
        try:
            scn[key] = []
        except Exception:
            pass

# ============================================================
# Clip/Context Utilities
# ============================================================

def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if mc:
        return mc
    # Fallback: erstes MovieClip in Datenbank
    for c in bpy.data.movieclips:
        return c
    return None


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
        # Notfalls ohne Override probieren – manche Ops sind tolerant
        return op_callable(**kwargs)
    override = {
        "window": window,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _delete_selected_tracks(confirm: bool = True) -> None:
    def _op(**kw):
        return bpy.ops.clip.delete_track(**kw)
    _run_in_clip_context(_op, confirm=confirm)

# ============================================================
# Track/Marker Utilities
# ============================================================

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


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

# ============================================================
# Pre-Pass: Selektionsbasierte Löschung zuvor erzeugter Tracks
# ============================================================

def detect_prepass_cleanup(context: bpy.types.Context, *, confirm: bool = True) -> Dict[str, Any]:
    """Selektionsbasierter Pre-Cleanup vor Detect.

    Löscht alle zuvor vom Detect erzeugten Tracks, indem sie selektiert und
    dann über bpy.ops.clip.delete_track(confirm=...) entfernt werden.
    Grundlage ist das Tag track["__detect_created"] == True.
    """
    scn = context.scene
    mc = _get_movieclip(context)
    if not mc:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = mc.tracking

    # 1) Alles deselektieren
    _deselect_all(tracking)

    # 2) Alle vom letzten Detect getaggten Tracks selektieren
    to_select = 0
    for tr in tracking.tracks:
        try:
            if bool(tr.get("__detect_created", False)):
                tr.select = True
                to_select += 1
        except Exception:
            pass

    removed = 0

    # 3) Ausgewählte Tracks über Operator löschen (selektionbasiert)
    if to_select > 0:
        try:
            _delete_selected_tracks(confirm=confirm)
            removed = to_select
        except Exception:
            # Fallback, falls Operator-Kontext versagt → harte Entfernung
            for tr in list(tracking.tracks):
                try:
                    if tr.select:
                        tracking.tracks.remove(tr)
                        removed += 1
                except Exception:
                    pass

    # 4) Persistenzlisten/Legacy aufräumen (keine Namenslogik mehr)
    _try_set_scene_list(scn, DETECT_PREV_KEY, [])

    print(f"[DetectDebug] Pre-Cleanup: removed={removed} (selection-based)")
    return {"status": "OK", "removed": removed}

# ============================================================
# Kern: Detect-Operator-Wrapper
# ============================================================

def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    # Skaliert Parameter leicht in Abhängigkeit vom threshold
    factor = math.log10(max(float(threshold), 1e-6) * 1e6) / 6.0
    margin = max(1, int(int(margin_base) * factor))
    min_distance = max(1, int(int(min_distance_base) * factor))
    return margin, min_distance


def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    """Kontext-sicherer Aufruf von bpy.ops.clip.detect_features mit skalierten Parametern.
    Rückgabe: Anzahl selektierter Tracks (nur loser Indikator; Blender selektiert dort idR nicht).
    """
    margin, min_distance = _scaled_params(float(threshold), int(margin_base), int(min_distance_base))

    def _op(**kw):
        # robust: einige Builds kennen nicht alle Kwargs
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    try:
        _run_in_clip_context(
            _op,
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        print("[DetectDebug] detect_features failed in override:", ex)
        raise

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ============================================================
# Ein einzelner Detect-Pass (mit Korridor & Near-Duplicate-Filter)
# ============================================================

def run_detect_once(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    marker_adapt: Optional[int] = None,
    min_marker: Optional[int] = None,
    max_marker: Optional[int] = None,
    margin_base: Optional[int] = None,        # px; Default = 2.5% Bildbreite
    min_distance_base: Optional[int] = None,  # px; Default = 5% Bildbreite
    close_dist_rel: float = 0.01,             # 1% Bildbreite
    handoff_to_pipeline: bool = False,
) -> Dict[str, Any]:
    scn = context.scene
    scn[_LOCK_KEY] = True

    try:
        clip = _get_movieclip(context)
        if not clip:
            return {"status": "FAILED", "reason": "no_movieclip"}

        tracking = clip.tracking
        settings = tracking.settings
        width, height = int(clip.size[0]), int(clip.size[1])

        # Frame setzen
        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:
                pass
        frame = int(scn.frame_current)

        # PRE-PASS (selektionsbasiert)
        detect_prepass_cleanup(context, confirm=True)

        # Threshold bestimmen
        if threshold is None:
            base_thr = float(getattr(settings, "default_correlation_min", 0.75))
            try:
                last_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, base_thr))
            except Exception:
                last_thr = base_thr
            threshold = max(1e-6, float(last_thr))
        else:
            threshold = max(1e-6, float(threshold))

        # Zielkorridor
        if marker_adapt is None:
            try:
                marker_adapt = int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
            except Exception:
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

        # Snapshot & bestehende Markerpositionen
        initial_names = {_coerce_utf8_str(t.name) or str(t.name) for t in tracking.tracks}
        existing_px = _collect_existing_positions(tracking, frame, width, height)

        # Detect aufrufen
        _deselect_all(tracking)
        try:
            perform_marker_detection(
                clip, tracking, float(threshold), int(margin_base), int(min_distance_base)
            )
        except Exception as ex:
            print("[DetectDebug] FAILED: detect_features op:", ex)
            try:
                scn["detect_status"] = "failed"
            except Exception:
                pass
            return {"status": "FAILED", "reason": "detect_features_failed"}

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Neue Tracks bestimmen
        tracks = tracking.tracks
        new_tracks_raw = [t for t in tracks if (_coerce_utf8_str(t.name) or str(t.name)) not in initial_names]
        added_names = {_coerce_utf8_str(t.name) or str(t.name) for t in new_tracks_raw}

        # Near-Duplicates entfernen (gegen Cluster auf identischer Stelle)
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
                _delete_selected_tracks(confirm=True)
            except Exception:
                # Fallback: direkter Remove
                for t in list(close_tracks):
                    try:
                        tracking.tracks.remove(t)
                    except Exception:
                        pass

        close_set = {t.name for t in close_tracks}
        cleaned_tracks = [t for t in new_tracks_raw if t.name not in close_set]
        anzahl_neu = len(cleaned_tracks)

        # **Taggen**: alle in diesem Detect-Lauf erstellten (bereinigten) Tracks kennzeichnen,
        # damit der nächste Pre-Cleanup sie über Selektion löschen kann.
        for t in cleaned_tracks:
            try:
                t["__detect_created"] = True
            except Exception:
                pass

        print(
            "[DetectDebug] Frame=%d | anzahl_neu=%d | marker_min=%d | marker_max=%d | "
            "marker_adapt=%d | threshold_old=%.6f"
            % (frame, anzahl_neu, int(min_marker), int(max_marker), int(marker_adapt), float(threshold))
        )

        # Korridorprüfung → RUNNING (adaptive threshold)
        if anzahl_neu < int(min_marker) or anzahl_neu > int(max_marker):
            # alles, was wir gerade erzeugt hatten, wieder entfernen (sauberer Neustart)
            if added_names:
                _deselect_all(tracking)
                for t in tracks:
                    if (_coerce_utf8_str(t.name) or str(t.name)) in added_names:
                        t.select = True
                try:
                    _delete_selected_tracks(confirm=True)
                except Exception:
                    pass
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:
                    pass

            # Threshold neu justieren
            new_threshold = max(
                float(threshold) * ((anzahl_neu + 0.1) / float(max(1, int(marker_adapt)))),
                1e-4,
            )
            try:
                scn[DETECT_LAST_THRESHOLD_KEY] = float(new_threshold)
                scn["detect_status"] = "running"
                _try_set_scene_list(scn, DETECT_PREV_KEY, [])  # legacy leer
            except Exception:
                pass

            print(
                "[DetectDebug] RUNNING → new_threshold=%.6f (old=%.6f, adapt=%d) | anzahl_neu=%d | corridor=[%d..%d]"
                % (
                    float(new_threshold),
                    float(threshold),
                    int(marker_adapt),
                    int(anzahl_neu),
                    int(min_marker),
                    int(max_marker),
                )
            )

            return {
                "status": "RUNNING",
                "new_tracks": int(anzahl_neu),
                "threshold": float(new_threshold),
                "frame": int(frame),
                "created_names": [],  # Namen sind hier nicht mehr relevant
            }

        # READY: Erfolg → (legacy) Liste leeren, Schwelle merken
        try:
            _try_set_scene_list(scn, DETECT_PREV_KEY, [])  # wir verlassen uns auf Tagging, nicht auf Namen
            scn[DETECT_LAST_THRESHOLD_KEY] = float(threshold)
        except Exception:
            pass

        # Handoff-Gate
        try:
            if handoff_to_pipeline:
                scn["detect_status"] = "success"
                scn["pipeline_do_not_start"] = False
            else:
                scn["detect_status"] = "standalone_success"
                scn["pipeline_do_not_start"] = True
        except Exception:
            pass

        # Airbag gegen direkt folgenden CleanShort (falls in deiner Pipeline genutzt)
        try:
            scn["__skip_clean_short_once"] = True
            _try_set_scene_list(scn, "__just_created_names", [])  # optional
        except Exception:
            pass

        print(
            "[DetectDebug] READY | anzahl_neu=%d liegt im Korridor [%d..%d] | threshold_keep=%.6f"
            % (int(anzahl_neu), int(min_marker), int(max_marker), float(threshold))
        )

        return {
            "status": "READY",
            "new_tracks": int(anzahl_neu),
            "threshold": float(threshold),
            "frame": int(frame),
            "created_names": [],  # wir speichern keine Namen mehr ab
        }

    except Exception as ex:
        print("[DetectDebug] FAILED:", ex)
        try:
            scn["detect_status"] = "failed"
        except Exception:
            pass
        return {"status": "FAILED", "reason": str(ex)}
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass

# ============================================================
# Mehrfach-Wrapper (adaptive Re-Runs)
# ============================================================

def run_detect_adaptive(
    context: bpy.types.Context,
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
