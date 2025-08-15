# detect_neu.py — adaptive Merker-Detektion mit auflösungsbasierten Parametern,
#                 robustem Cleanup, UI-Kontext-Override, Handoff-Gate (wie alt)
#                 und Schutz vor Endlosschleifen.
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
# - Cleanup: Pre-Pass + In-Pass (Operator→Fallback)
# - Zusatz-Airbag: __skip_clean_short_once / __just_created_names

import bpy
import math
from typing import Dict, Any, Optional, List, Tuple, Iterable

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
    "clean_short_tracks",
]

_LOCK_KEY = "__detect_lock"


# ---------------------------------------------------------------------------
# Kontext-Utilities (CLIP_EDITOR-Override)
# ---------------------------------------------------------------------------

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
    target = set(names_to_remove)
    for t in list(tracking.tracks):
        if t.name in target:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
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


# ---------------------------------------------------------------------------
# Feature-Detektion (mit Kontext-Override)
# ---------------------------------------------------------------------------

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
    except Exception as ex:
        print("[DetectDebug] detect_features failed in override:", ex)
        raise
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------------
# EIN einzelner Detect‑Pass
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
    handoff_to_pipeline: bool = False,        # <<< NEU: wie alte Version (Operator)
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
            except Exception:
                pass
        frame = int(scn.frame_current)

        # PRE‑PASS Cleanup (Reste aus fehlgeschlagenen Runs)
        prev_names = set(scn.get("detect_prev_names", []) or [])
        if prev_names:
            _remove_tracks_by_name(tracking, prev_names)
            scn["detect_prev_names"] = []
            try:
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            except Exception:
                pass

        # Threshold laden
        if threshold is None:
            threshold = float(
                scn.get(
                    "last_detection_threshold",
                    float(getattr(settings, "default_correlation_min", 0.75)),
                )
            )
        threshold = max(1e-6, float(threshold))

        # Zielkorridor
        if marker_adapt is None:
            marker_adapt = int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
        safe_adapt = max(1, int(marker_adapt))

        # Hier eher großzügig – dein Helper setzt min/max ≈ ±10 % um adapt
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
        initial_names = {t.name for t in tracking.tracks}
        existing_px = _collect_existing_positions(tracking, frame, width, height)

        # Detect
        _deselect_all(tracking)
        try:
            perform_marker_detection(
                clip, tracking,
                float(threshold),
                int(margin_base), int(min_distance_base),
            )
        except Exception as ex:
            print("[DetectDebug] FAILED: Operator bpy.ops.clip.detect_features failed:", ex)
            scn["detect_status"] = "failed"
            return {"status": "FAILED", "reason": "detect_features_failed"}

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Neue Tracks
        tracks = tracking.tracks
        new_tracks_raw = [t for t in tracks if t.name not in initial_names]
        added_names = {t.name for t in new_tracks_raw}

        # Near‑Duplicates entfernen
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
                        dx = x - ex; dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(tr)
                            break

        if close_tracks:
            _deselect_all(tracking)
            for t in close_tracks:
                t.select = True
            try:
                _run_in_clip_context(lambda **kw: bpy.ops.clip.delete_track(**kw))
            except Exception:
                _remove_tracks_by_name(tracking, {t.name for t in close_tracks})

        close_set = {t.name for t in close_tracks}
        cleaned_tracks = [t for t in new_tracks_raw if t.name not in close_set]
        anzahl_neu = len(cleaned_tracks)
        created_names = [t.name for t in cleaned_tracks]

        print(
            "[DetectDebug] Frame=%d | anzahl_neu=%d | marker_min=%d | marker_max=%d | "
            "marker_adapt=%d | threshold_old=%.6f"
            % (frame, anzahl_neu, int(min_marker), int(max_marker), int(marker_adapt), float(threshold))
        )

        # Korridorprüfung
        if anzahl_neu < int(min_marker) or anzahl_neu > int(max_marker):
            remaining_after_delete: set[str] = set()

            if added_names:
                _deselect_all(tracking)
                for t in tracks:
                    if t.name in added_names:
                        t.select = True
                try:
                    _run_in_clip_context(lambda **kw: bpy.ops.clip.delete_track(**kw))
                except Exception:
                    pass

                still_there = {t.name for t in tracking.tracks if t.name in added_names}
                if still_there:
                    _remove_tracks_by_name(tracking, still_there)
                    remaining_after_delete = {
                        n for n in still_there if n in {t.name for t in tracking.tracks}
                    }
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:
                    pass

            new_threshold = max(
                float(threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            scn["last_detection_threshold"] = float(new_threshold)
            scn["detect_status"] = "running"  # <<< Neu gesetzt

            print(
                "[DetectDebug] RUNNING → new_threshold=%.6f (old=%.6f, adapt=%d) | anzahl_neu=%d | corridor=[%d..%d]"
                % (float(new_threshold), float(threshold), int(marker_adapt),
                   int(anzahl_neu), int(min_marker), int(max_marker))
            )

            scn["detect_prev_names"] = list(remaining_after_delete) if remaining_after_delete else []

            return {
                "status": "RUNNING",
                "new_tracks": int(anzahl_neu),
                "threshold": float(new_threshold),
                "frame": int(frame),
                "created_names": created_names,
            }

        # READY: Erfolg
        scn["detect_prev_names"] = []
        scn["last_detection_threshold"] = float(threshold)

        # === Handoff-Gate (wie alt) ===
        if handoff_to_pipeline:
            scn["detect_status"] = "success"
            scn["pipeline_do_not_start"] = False
        else:
            scn["detect_status"] = "standalone_success"
            scn["pipeline_do_not_start"] = True  # <<< WICHTIG: Pipeline (z. B. CleanShort) erstmal NICHT starten
        # ===============================

        # Airbag gegen CleanShort direkt danach (falls Koordinator Flag ignoriert)
        scn["__skip_clean_short_once"] = True
        scn["__just_created_names"] = created_names

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

    except Exception as ex:
        print("[DetectDebug] FAILED:", ex)
        scn["detect_status"] = "failed"  # wie alt
        return {"status": "FAILED", "reason": str(ex)}
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Optionaler Mehrfach‑Wrapper
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


# ---------------------------------------------------------------------------
# Clean-Short Helper (Airbag, falls Koordinator nicht auf Gate hört)
# ---------------------------------------------------------------------------

def clean_short_tracks(
    context,
    *,
    frames: int,
    action: str = "DELETE_TRACK",
) -> Dict[str, Any]:
    scn = context.scene

    # Falls Gate aktiv ist: CleanShort aussetzen
    if scn.get("pipeline_do_not_start", False):
        print("[CleanShort] blocked by pipeline_do_not_start")
        return {"CANCELLED": True}

    # Einmaliger Skip direkt nach READY
    if scn.get("__skip_clean_short_once"):
        print("[CleanShort] skipped once to protect fresh detects")
        scn["__skip_clean_short_once"] = False
        return {"CANCELLED": True}

    fresh = set(scn.get("__just_created_names", []) or [])
    try:
        clip = _resolve_clip(context)
        if not clip:
            print("[CleanShort] no clip")
            return {"CANCELLED": True}
        tracking = clip.tracking

        # Auswahl: alle selektieren, dann frische ausschließen
        for t in tracking.tracks:
            t.select = True
        if fresh:
            for t in tracking.tracks:
                if t.name in fresh:
                    t.select = False

        def _op(**kw):
            return bpy.ops.clip.clean_tracks(**kw)

        try:
            _run_in_clip_context(_op, frames=int(frames), error=0.0, action=str(action))
        except Exception as ex:
            print("[CleanShort] clean_tracks override failed:", ex)
            try:
                bpy.ops.clip.clean_tracks(frames=int(frames), error=0.0, action=str(action))
            except Exception as ex2:
                print("[CleanShort] clean_tracks fallback failed:", ex2)
                return {"CANCELLED": True}

        if fresh:
            scn["__just_created_names"] = []

        print(f"[CleanShort] Tracks < {int(frames)} Frames wurden bearbeitet. Aktion: {action}")
        return {"FINISHED": True}

    except Exception as ex:
        print("[CleanShort] FAILED:", ex)
        return {"CANCELLED": True}
