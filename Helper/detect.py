# Helper/detect.py
import bpy
import math
import time
from contextlib import contextmanager

__all__ = [
    "perform_marker_detection",
    "run_detect_adaptive",
    "run_detect_once",
]

# ---------------------------------------------------------------------------
# UI-Context Guard
# ---------------------------------------------------------------------------

def _find_clip_area(win):
    if not win or not getattr(win, "screen", None):
        return None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if reg:
                return area, reg
    return None, None

@contextmanager
def _ensure_clip_context(ctx, clip=None, *, allow_area_switch=True):
    """
    Stellt einen gültigen CLIP_EDITOR-Kontext bereit und liefert einen temp_override.
    """
    win = getattr(ctx, "window", None)
    area, region = _find_clip_area(win)
    switched = False
    old_type = None

    if not area and allow_area_switch and win and getattr(win, "screen", None) and win.screen.areas:
        area = win.screen.areas[0]
        old_type = area.type
        area.type = 'CLIP_EDITOR'
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        switched = True

    if not area or not region:
        yield None
        if switched and old_type is not None:
            area.type = old_type
        return

    space = area.spaces.active
    try:
        if getattr(space, "mode", None) != 'TRACKING':
            space.mode = 'TRACKING'
        if clip is not None:
            space.clip = clip
        elif getattr(space, "clip", None) is None:
            # kein harter Fallback – still lassen
            pass
    except Exception:
        pass

    override = {
        "window": win,
        "screen": getattr(win, "screen", None),
        "area": area,
        "region": region,
        "space_data": space,
        "scene": ctx.scene,
    }

    try:
        with bpy.context.temp_override(**override):
            yield override
    finally:
        if switched and old_type is not None:
            area.type = old_type

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _deselect_all(tracking):
    for t in tracking.tracks:
        t.select = False

def _remove_tracks_by_name(tracking, names_to_remove):
    if not names_to_remove:
        return 0
    removed = 0
    for t in list(tracking.tracks):
        if t.name in names_to_remove:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
                pass
    return removed

def _collect_existing_positions(tracking, frame, w, h):
    out = []
    for t in tracking.tracks:
        m = t.markers.find_frame(frame, exact=True)
        if m and not m.mute:
            out.append((m.co[0] * w, m.co[1] * h))
    return out

def _resolve_clip_from_context(context):
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None

def _sync_viewer_frame_in_override(ctx, frame:int):
    """
    Kritisch: Szene-Frame setzen UND sofort redrawen – innerhalb des UI-Overrides.
    Dadurch zeigt der Viewer sicher den Ziel-Frame, bevor detect_features läuft.
    """
    try:
        ctx.scene.frame_set(int(frame))
    except Exception:
        pass
    # Sicherer Soft-Redraw (keine Styles setzen, nur ein Swap)
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Legacy-Helper (API-kompatibel)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus und liefert die Anzahl
    selektierter Tracks zurück (Legacy-Kontrakt).
    WICHTIG: Viewer-Frame wird im selben Override synchronisiert.
    """
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    # Kontext-sicherer Operator-Call inkl. Frame-Sync
    with _ensure_clip_context(bpy.context, clip=clip, allow_area_switch=True) as ovr:
        if ovr is None:
            raise RuntimeError("CLIP_EDITOR-Kontext nicht verfügbar (perform_marker_detection).")

        # Frame des Viewers mit der Szene synchronisieren
        _sync_viewer_frame_in_override(bpy.context, bpy.context.scene.frame_current)

        bpy.ops.clip.detect_features(
            margin=margin,
            min_distance=min_distance,
            threshold=float(threshold),
        )

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------------
# Adaptive Detect
# ---------------------------------------------------------------------------

def run_detect_adaptive(
    context: bpy.types.Context,
    *,
    detection_threshold: float = -1.0,
    marker_adapt: int = -1,
    min_marker: int = -1,
    max_marker: int = -1,
    frame: int = 0,
    margin_base: int = -1,
    min_distance_base: int = -1,
    close_dist_rel: float = 0.0,
    handoff_to_pipeline: bool = False,
    max_attempts: int = 20,
) -> dict:
    scn = context.scene
    scn["detect_status"] = "pending"

    if scn.get("tracking_pipeline_active", False):
        scn["detect_status"] = "failed"
        return {"status": "cancelled", "reason": "pipeline_active"}

    clip = _resolve_clip_from_context(context)
    if clip is None:
        scn["detect_status"] = "failed"
        return {"status": "cancelled", "reason": "no_clip"}

    tracking = clip.tracking
    settings = tracking.settings
    image_width = int(clip.size[0])

    # Threshold-Start
    if detection_threshold >= 0.0:
        detection_threshold = float(detection_threshold)
    else:
        try:
            default_min = float(getattr(settings, "default_correlation_min", 0.75))
        except Exception:
            default_min = 0.75
        try:
            detection_threshold = float(scn.get("last_detection_threshold", default_min))
        except Exception:
            detection_threshold = default_min

    if not (0.0 < float(detection_threshold) <= 1.0):
        detection_threshold = max(min(float(detection_threshold), 1.0), 1e-4)
    scn["last_detection_threshold"] = float(detection_threshold)
    print(f"[Detect] Start-Threshold={detection_threshold:.6f}")

    # Bounds
    adapt = int(marker_adapt) if marker_adapt >= 0 else int(scn.get("marker_adapt", 20))
    basis = int(scn.get("marker_basis", max(adapt, 20)))
    basis_for_bounds = int(adapt * 1.1) if adapt > 0 else int(basis)

    if min_marker >= 0:
        min_marker = int(min_marker)
    else:
        min_marker = int(scn.get("marker_min", basis_for_bounds * 0.9))

    if max_marker >= 0:
        max_marker = int(max_marker)
    else:
        max_marker = int(scn.get("marker_max", basis_for_bounds * 1.1))

    print(f"[Detect] Verwende min_marker={min_marker}, max_marker={max_marker} "
          f"(Scene: min={scn.get('marker_min')}, max={scn.get('marker_max')})")

    # Bases
    margin_base = margin_base if margin_base >= 0 else max(1, int(image_width * 0.025))
    min_distance_base = min_distance_base if min_distance_base >= 0 else max(1, int(image_width * 0.05))

    # --- WICHTIG: Frame vor dem ersten Detect IM OVERRIDE synchronisieren ---
    if frame and frame > 0:
        with _ensure_clip_context(context, clip=clip, allow_area_switch=True):
            _sync_viewer_frame_in_override(context, int(frame))

    # Cleanup aus Vorlauf
    prev_names = set(scn.get("detect_prev_names", []) or [])
    if prev_names:
        _remove_tracks_by_name(tracking, prev_names)
        scn["detect_prev_names"] = []

    attempt = 0
    width, height = clip.size

    while attempt < max_attempts:
        current_frame = int(scn.frame_current)

        # Snapshots
        tracks = tracking.tracks
        existing_positions = _collect_existing_positions(tracking, current_frame, width, height)
        initial_track_names = {t.name for t in tracks}
        len_before = len(tracks)

        # Detect (führt intern Frame-Sync nochmals aus)
        perform_marker_detection(
            clip,
            tracking,
            float(detection_threshold),
            int(margin_base),
            int(min_distance_base),
        )

        # Redraw
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        # Materialisierung abwarten
        materialized = False
        for _ in range(50):
            if len(tracking.tracks) != len_before:
                names_now = {t.name for t in tracking.tracks}
                if names_now != initial_track_names:
                    materialized = True
                    break
            time.sleep(0.01)

        # PROCESS
        tracks = tracking.tracks
        new_tracks = [t for t in tracks if t.name not in initial_track_names]

        rel = close_dist_rel if close_dist_rel > 0.0 else 0.01
        distance_px = max(1, int(width * rel))
        thr2 = float(distance_px * distance_px)

        close_tracks = []
        if existing_positions and new_tracks:
            for tr in new_tracks:
                m = tr.markers.find_frame(current_frame, exact=True)
                if m and not m.mute:
                    x = m.co[0] * width
                    y = m.co[1] * height
                    for ex, ey in existing_positions:
                        dx = x - ex
                        dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(tr)
                            break

        if close_tracks:
            cleaned_names = {t.name for t in new_tracks if t not in close_tracks}
            _remove_tracks_by_name(tracking, {t.name for t in close_tracks})
            for t in tracking.tracks:
                t.select = (t.name in cleaned_names)

        close_set = set(close_tracks)
        cleaned_tracks = [t for t in new_tracks if t not in close_set]
        anzahl_neu = len(cleaned_tracks)

        if anzahl_neu < min_marker or anzahl_neu > max_marker:
            if cleaned_tracks:
                for t in tracks:
                    t.select = False
                for t in cleaned_tracks:
                    t.select = True
                with _ensure_clip_context(context, clip=clip, allow_area_switch=True) as ovr:
                    if ovr is not None:
                        try:
                            bpy.ops.clip.delete_track()
                        except Exception:
                            _remove_tracks_by_name(tracking, {t.name for t in cleaned_tracks})
                    else:
                        _remove_tracks_by_name(tracking, {t.name for t in cleaned_tracks})

            safe_adapt = max(adapt, 1)
            detection_threshold = max(
                float(detection_threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            scn["last_detection_threshold"] = float(detection_threshold)
            attempt += 1
            continue

        try:
            scn["detect_prev_names"] = [t.name for t in cleaned_tracks]
        except Exception:
            scn["detect_prev_names"] = []

        scn["detect_status"] = "success"
        scn["pipeline_do_not_start"] = False

        try:
            from .bidirectional_track import run_bidirectional_track
            run_bidirectional_track(context)
        except Exception as e:
            print(f"[Detect] Tracking-Start fehlgeschlagen: {e}")

        return {
            "status": "success",
            "attempts": attempt + 1,
            "new_tracks": anzahl_neu,
            "threshold": float(detection_threshold),
            "prev_names": list(scn.get("detect_prev_names", [])),
        }

    scn["detect_status"] = "failed"
    return {
        "status": "failed",
        "attempts": attempt,
        "threshold": float(detection_threshold),
    }

# ---------------------------------------------------------------------------
# Alias für Abwärtskompatibilität
# ---------------------------------------------------------------------------

def run_detect_once(context, start_frame=None, **_):
    """
    Kompatibilitäts-Shim:
    - optional Frame setzen (im UI-Override)
    - dann adaptive Detection starten
    """
    if start_frame is not None and int(start_frame) > 0:
        clip = _resolve_clip_from_context(context)
        with _ensure_clip_context(context, clip=clip, allow_area_switch=True):
            _sync_viewer_frame_in_override(context, int(start_frame))

    try:
        return run_detect_adaptive(context)
    except TypeError:
        try:
            return run_detect_adaptive(context)
        except Exception as ex:
            print(f"[Detect] run_detect_once failed: {ex}")
            return {'CANCELLED'}
