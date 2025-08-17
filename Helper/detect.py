# Helper/detect.py — Detect ohne Namenszugriff (kein UTF-8-Risiko),
# pointer-basiert (as_pointer) mit Near-Duplicate-Clean, adaptiver Korridor-Logik,
# UI-Kontext-Override und ausführlichen Konsolen-Logs.
#
# Exportierte API:
#   - perform_marker_detection(...)
#   - run_detect_once(...)
#   - run_detect_adaptive(...)

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

import bpy

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
]

# Scene-Keys
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float – zuletzt verwendete Schwelle
_LOCK_KEY = "__detect_lock"

# =====================================================================
# Kontext-/Clip-Utilities
# =====================================================================

def _find_clip_editor_context():
    """Sucht einen CLIP_EDITOR-Kontext für Operatoren."""
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
    """Führt einen Operator im CLIP_EDITOR-Kontext aus (falls verfügbar)."""
    window, area, region, space = _find_clip_editor_context()
    if not (window and area and region and space):
        print("[DetectTrace] Kein CLIP_EDITOR-Kontext gefunden – Operator wird ohne Override versucht.")
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


def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Ermittelt den aktiven MovieClip oder nimmt das erste Clip-Objekt als Fallback."""
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if mc:
        return mc
    for c in bpy.data.movieclips:
        return c
    return None

# =====================================================================
# Track/Marker-Utilities
# =====================================================================

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


def _delete_selected_tracks(confirm: bool = True) -> None:
    def _op(**kw):
        return bpy.ops.clip.delete_track(**kw)
    _run_in_clip_context(_op, confirm=confirm)


def _collect_existing_positions(
    tracking: bpy.types.MovieTracking, frame: int, w: int, h: int
) -> List[Tuple[float, float]]:
    """Positions-Snapshot aller Marker am Frame (für Near-Duplicate-Erkennung)."""
    out: List[Tuple[float, float]] = []
    for t in tracking.tracks:
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0] * w, m.co[1] * h))
    return out

# =====================================================================
# Kern: detect_features-Wrapper
# =====================================================================

def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    """Skalierung von margin/min_distance in Abhängigkeit von threshold."""
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
    """Kontext-sicherer detect_features-Aufruf mit Logs."""
    margin, min_distance = _scaled_params(float(threshold), int(margin_base), int(min_distance_base))

    def _op(**kw):
        # einige Builds tolerieren nicht alle Kwargs → fallback ohne Kwargs
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    print(
        f"[DetectTrace] detect_features: thr={threshold:.6f}, margin={margin}, "
        f"min_dist={min_distance}"
    )
    t0 = time.perf_counter()
    try:
        _run_in_clip_context(
            _op,
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        dt = (time.perf_counter() - t0) * 1000.0
        print(f"[DetectError] detect_features Exception ({dt:.1f} ms): {ex}")
        raise
    dt = (time.perf_counter() - t0) * 1000.0
    print(f"[DetectTrace] detect_features DONE in {dt:.1f} ms")
    # Blender selektiert hier nicht zwingend; Rückgabe ist nur ein Indikator
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# =====================================================================
# Ein einzelner Detect-Pass (pointer-basiert)
# =====================================================================

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
    """Führt genau eine Detect-Runde aus (READY, RUNNING, FAILED)."""
    scn = context.scene
    scn[_LOCK_KEY] = True

    # *** defensive Vorinitialisierung für saubere Logs bei frühen Abbrüchen ***
    frame: int = int(getattr(scn, "frame_current", 0))
    before_ids: set[int] = set()
    tracks_list: List[bpy.types.MovieTrackingTrack] = []
    new_tracks_raw: List[bpy.types.MovieTrackingTrack] = []
    close_tracks: List[bpy.types.MovieTrackingTrack] = []
    cleaned_tracks: List[bpy.types.MovieTrackingTrack] = []
    anzahl_neu: int = 0

    try:
        clip = _get_movieclip(context)
        if not clip:
            print("[DetectError] Kein MovieClip verfügbar.")
            return {"status": "FAILED", "reason": "no_movieclip"}

        tracking = clip.tracking
        settings = tracking.settings
        width, height = int(clip.size[0]), int(clip.size[1])

        # Frame setzen
        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception as ex:
                print(f"[DetectError] frame_set({start_frame}) Exception: {ex}")
        frame = int(scn.frame_current)

        # Schwelle bestimmen
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

        print(
            "[DetectTrace] START "
            f"| frame={frame} | thr_in={threshold:.6f} | adapt={safe_adapt} "
            f"| corridor=[{min_marker}..{max_marker}] | bases: margin={margin_base}, min_dist={min_distance_base}"
        )

        # Snapshot vor Detect (Objekt-Identität)
        before_ids = {t.as_pointer() for t in tracking.tracks}
        print(f"[DetectDebug] Tracks BEFORE: {len(before_ids)} (by pointer)")

        # Positionssnapshot für Near-Duplicates
        existing_px = _collect_existing_positions(tracking, frame, width, height)
        print(f"[DetectDebug] Existing marker positions at frame {frame}: {len(existing_px)}")

        # Detect aufrufen
        _deselect_all(tracking)
        try:
            perform_marker_detection(
                clip, tracking, float(threshold), int(margin_base), int(min_distance_base)
            )
        except Exception as ex:
            print("[DetectError] detect_features op FAILED:", ex)
            try:
                scn["detect_status"] = "failed"
            except Exception:
                pass
            return {"status": "FAILED", "reason": "detect_features_failed"}

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Nach Detect: alle Tracks listen, neue nur per Pointer ermitteln (keine Namen!)
        tracks_list = list(tracking.tracks)
        new_tracks_raw = [t for t in tracks_list if t.as_pointer() not in before_ids]
        print(f"[DetectDebug] New tracks (raw, pointer-based): {len(new_tracks_raw)}")

        # Near-Duplicates filtern
        rel = close_dist_rel if close_dist_rel > 0.0 else 0.01
        distance_px = max(1, int(width * rel))
        thr2 = float(distance_px * distance_px)

        close_tracks = []
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
            print(f"[DetectDebug] Near-duplicates found: {len(close_tracks)} → deleting selection")
            _deselect_all(tracking)
            for t in close_tracks:
                t.select = True
            try:
                _delete_selected_tracks(confirm=True)
            except Exception as ex:
                print(f"[DetectError] delete_track operator failed, fallback remove: {ex}")
                for t in list(close_tracks):
                    try:
                        tracking.tracks.remove(t)
                    except Exception:
                        pass

        # Bereinigte neue Tracks (ohne Near-Duplicates)
        close_ids = {t.as_pointer() for t in close_tracks}
        cleaned_tracks = [t for t in new_tracks_raw if t.as_pointer() not in close_ids]
        anzahl_neu = len(cleaned_tracks)

        print(
            "[DetectDebug] Frame=%d | anzahl_neu=%d | marker_min=%d | marker_max=%d | "
            "marker_adapt=%d | threshold_old=%.6f"
            % (frame, anzahl_neu, int(min_marker), int(max_marker), int(marker_adapt), float(threshold))
        )

        # Korridorprüfung → RUNNING (adaptive threshold)
        if anzahl_neu < int(min_marker) or anzahl_neu > int(max_marker):
            # innerhalb DESSENSLBEN Runs: die gerade erzeugten Tracks wieder entfernen (selektiv)
            if cleaned_tracks:
                print(f"[DetectTrace] Corridor miss → remove {len(cleaned_tracks)} new tracks (this run)")
                _deselect_all(tracking)
                for t in cleaned_tracks:
                    t.select = True
                try:
                    _delete_selected_tracks(confirm=True)
                except Exception as ex:
                    print(f"[DetectError] delete_track operator failed on corridor-miss: {ex}")
                    for t in list(cleaned_tracks):
                        try:
                            tracking.tracks.remove(t)
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
            }

        # READY: Erfolg → Schwelle merken
        try:
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

        # Am Ende: neue Marker selektiert lassen (exklusiv)
        try:
            _deselect_all(tracking)
            for t in cleaned_tracks:
                t.select = True
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            print(f"[DetectTrace] READY: selected {len(cleaned_tracks)} new tracks (exclusive)")
        except Exception as ex:
            print(f"[DetectError] Final selection failed: {ex}")

        print(
            "[DetectDebug] READY | anzahl_neu=%d liegt im Korridor [%d..%d] | threshold_keep=%.6f"
            % (int(anzahl_neu), int(min_marker), int(max_marker), float(threshold))
        )

        return {
            "status": "READY",
            "new_tracks": int(anzahl_neu),
            "threshold": float(threshold),
            "frame": int(frame),
        }

    except Exception as ex:
        print("[DetectError] FAILED:", ex)
        try:
            scn["detect_status"] = "failed"
        except Exception:
            pass
        # Wichtig: Status-Objekt immer konsistent zurückgeben, inkl. Frame
        return {"status": "FAILED", "reason": str(ex), "frame": int(frame)}
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass

# =====================================================================
# Mehrfach-Wrapper (adaptive Re-Runs)
# =====================================================================

def run_detect_adaptive(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    max_attempts: int = 8,
    **kwargs,
) -> Dict[str, Any]:
    """Mehrfachausführung von run_detect_once bis READY oder FAILED."""
    last: Dict[str, Any] = {}
    for attempt in range(max_attempts):
        print(f"[DetectTrace] ADAPTIVE attempt {attempt + 1}/{max_attempts}")
        last = run_detect_once(context, start_frame=start_frame, **kwargs)
        st = last.get("status")
        if st in ("READY", "FAILED"):
            print(f"[DetectTrace] ADAPTIVE STOP status={st}")
            return last
        # beim nächsten Versuch mit dem gleichen Frame weitermachen (oder last-frame)
        start_frame = last.get("frame", start_frame)
    print("[DetectTrace] ADAPTIVE max_attempts_exceeded")
    return last or {"status": "FAILED", "reason": "max_attempts_exceeded"}
