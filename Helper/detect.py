# Helper/detect.py — robuste Helper-Variante mit garantiertem Fail-Cleanup
# Parität zum funktionierenden Operator:
# - Start-Cleanup: scene['detect_prev_names'] wird zu Laufbeginn gelöscht
# - Near-Duplicate-Filter relativ zur Bildbreite
# - End-Cleanup bei Fehlversuch: bereinigte neue Tracks dieses Versuchs werden gelöscht
# - Adaptive Threshold-Anpassung proportional zur Abweichung vom Zielkorridor
# Härtungen:
# - Sicherer CLIP_EDITOR-Kontext (space.mode='TRACKING', Clip wird immer gesetzt)
# - Verifizierte Löschung mit Operator+Fallback auf Datablock-API

import bpy
import math
from contextlib import contextmanager

__all__ = [
    "perform_marker_detection",
    "run_detect_adaptive",
    "run_detect_once",
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _deselect_all(tracking):
    for t in tracking.tracks:
        t.select = False


def _remove_tracks_by_name(tracking, names_to_remove):
    """Robustes Entfernen von Tracks per Datablock-API (ohne UI-Selektion)."""
    if not names_to_remove:
        return 0
    removed = 0
    # Kopie iterieren, da wir aus der Sammlung löschen
    for t in list(tracking.tracks):
        if t.name in names_to_remove:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
                pass
    return removed


def _collect_existing_positions(tracking, frame, w, h):
    """Positionen existierender Marker (x,y in px) im Ziel-Frame sammeln."""
    out = []
    for t in tracking.tracks:
        m = t.markers.find_frame(frame, exact=True)
        if m and not m.mute:
            out.append((m.co[0] * w, m.co[1] * h))
    return out


def _resolve_clip(context):
    """Aktiven MovieClip ermitteln (Space → Clip, sonst erster Clip im File)."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# UI-Context Guard (nur lokal in diesem Modul verwendet)
# ---------------------------------------------------------------------------

def _find_clip_area(win):
    if not win or not getattr(win, "screen", None):
        return None, None
    for area in win.screen.areas:
        if area.type == "CLIP_EDITOR":
            reg = next((r for r in area.regions if r.type == "WINDOW"), None)
            if reg:
                return area, reg
    return None, None


@contextmanager
def _ensure_clip_context(ctx, clip=None, *, allow_area_switch=True):
    """
    Sichert einen gültigen CLIP_EDITOR-Kontext (area/region/space_data, TRACKING-Mode, Clip gesetzt).
    Greift nur lokal; vermeidet Seiteneffekte außerhalb dieses Calls.
    """
    win = getattr(ctx, "window", None)
    area, region = _find_clip_area(win)

    switched = False
    old_type = None
    if area is None and allow_area_switch and win and getattr(win, "screen", None):
        try:
            area = win.screen.areas[0]
            old_type = area.type
            area.type = "CLIP_EDITOR"
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            switched = True
        except Exception:
            area = None
            region = None

    override = {}
    if area and region:
        space = area.spaces.active
        override["area"] = area
        override["region"] = region
        override["space_data"] = space
        # Mode hart auf TRACKING setzen
        try:
            if getattr(space, "mode", None) != 'TRACKING':
                space.mode = 'TRACKING'
        except Exception:
            pass
        # Clip immer setzen (auch wenn bereits einer vorhanden ist)
        if clip is not None:
            try:
                if getattr(space, "clip", None) is not clip:
                    space.clip = clip
            except Exception:
                pass

    try:
        if override:
            with ctx.temp_override(**override):
                yield
        else:
            yield
    finally:
        if switched:
            try:
                area.type = old_type
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Verifizierte Löschung: Operator + API-Fallback
# ---------------------------------------------------------------------------

def _delete_tracks_hard(tracking, tracks_or_names):
    """
    Löscht Tracks robust: versucht Operator (mit Selektion) und prüft anschließend.
    Nicht entfernte Ziele werden per Datablock-API gelöscht.
    Rückgabe: Anzahl effektiv gelöschter Ziel-Tracks.
    """
    if not tracks_or_names:
        return 0

    # Namensmenge auflösen
    if hasattr(tracks_or_names[0], "name"):
        target_names = {t.name for t in tracks_or_names}
    else:
        target_names = set(tracks_or_names)

    # Operator-Versuch (Selektion herstellen)
    for t in tracking.tracks:
        t.select = False
    for t in tracking.tracks:
        if t.name in target_names:
            t.select = True

    op_ok = False
    try:
        res = bpy.ops.clip.delete_track()
        op_ok = (res == {'FINISHED'})
    except Exception:
        op_ok = False

    # Verifizieren – noch vorhandene Ziele bestimmen
    still = {t.name for t in tracking.tracks if t.name in target_names}
    if not still:
        print(f"[DeleteHard] op_ok={op_ok}, fallback_removed=0, still_left=0")
        return len(target_names)

    # Fallback über Datablock-API
    removed_fb = _remove_tracks_by_name(tracking, still)
    remain = {t.name for t in tracking.tracks if t.name in target_names}
    print(f"[DeleteHard] op_ok={op_ok}, fallback_removed={removed_fb}, still_left={len(remain)}")
    return len(target_names) - len(remain)


# ---------------------------------------------------------------------------
# detect_features Wrapper (Skalierung wie im Operator)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus und liefert die Anzahl
    selektierter Tracks zurück (Legacy-Kontrakt).
    """
    # log-Skalierung robust gegenüber sehr kleinen Thresholds
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    try:
        bpy.ops.clip.detect_features(
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        print(f"[Detect] detect_features exception: {ex}")
        return 0

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------------
# Parameter-Aufbereitung (Parität zum Operator)
# ---------------------------------------------------------------------------

def _compute_bounds(context, clip, detection_threshold, marker_adapt, min_marker, max_marker):
    scene = context.scene
    tracking = clip.tracking
    settings = tracking.settings
    image_width = int(clip.size[0])

    # Threshold-Start
    if detection_threshold is not None and detection_threshold >= 0.0:
        thr = float(detection_threshold)
    else:
        thr = float(scene.get("last_detection_threshold",
                              float(getattr(settings, "default_correlation_min", 0.75))))
    thr = float(max(1e-4, min(1.0, thr)))

    # marker_adapt / Bounds
    if marker_adapt is not None and marker_adapt >= 0:
        adapt = int(marker_adapt)
    else:
        adapt = int(scene.get("marker_adapt", 20))
    adapt = max(1, adapt)

    basis = int(scene.get("marker_basis", max(adapt, 20)))
    basis_for_bounds = int(adapt * 1.1) if adapt > 0 else int(basis)

    mn = int(min_marker) if (min_marker is not None and min_marker >= 0) else int(basis_for_bounds * 0.9)
    mx = int(max_marker) if (max_marker is not None and max_marker >= 0) else int(basis_for_bounds * 1.1)

    # Bases für margin/min_distance
    margin_base = max(1, int(image_width * 0.025))
    min_distance_base = max(1, int(image_width * 0.05))

    return thr, adapt, mn, mx, margin_base, min_distance_base


# ---------------------------------------------------------------------------
# Nicht-modale Detection – Start-Cleanup + End-Cleanup (Fehlversuch)
# ---------------------------------------------------------------------------

def run_detect_once(
    context,
    *,
    start_frame=None,
    detection_threshold=-1.0,
    marker_adapt=-1,
    min_marker=-1,
    max_marker=-1,
    margin_base=-1,
    min_distance_base=-1,
    close_dist_rel=0.01,
    handoff_to_pipeline=False,
    use_override=True,
):
    """
    Rückgabe:
      {"status": "READY"/"RUNNING"/"FAILED",
       "new_tracks": int,
       "threshold": float,
       "frame": int}

    Verhalten wie der funktionierende Operator:
    - Am Start werden Namen aus scene['detect_prev_names'] entfernt (inter-run Cleanup).
    - Bei Fehlversuch (RUNNING) werden am Ende die bereinigten neuen Tracks gelöscht.
    """
    clip = _resolve_clip(context)
    if clip is None:
        return {"status": "FAILED", "reason": "no_clip"}

    scene = context.scene
    tracking = clip.tracking
    w, h = clip.size

    thr, adapt, mn, mx, mb, mdb = _compute_bounds(context, clip, detection_threshold, marker_adapt, min_marker, max_marker)
    if margin_base is not None and margin_base >= 0:
        mb = int(margin_base)
    if min_distance_base is not None and min_distance_base >= 0:
        mdb = int(min_distance_base)

    # --- Start: inter-run Cleanup wie Operator ---
    prev_names = set(scene.get("detect_prev_names", []) or [])
    if prev_names:
        removed_prev = _remove_tracks_by_name(tracking, prev_names)
        print(f"[DetectCleanup] start_removed_prev={removed_prev}, planned={len(prev_names)}")
        scene["detect_prev_names"] = []

    # Optional Frame setzen
    if start_frame is not None:
        try:
            scene.frame_set(int(start_frame))
        except Exception:
            pass

    frame = int(scene.frame_current)

    # Snapshot vor Detect
    _deselect_all(tracking)
    initial_names = {t.name for t in tracking.tracks}
    existing_positions = _collect_existing_positions(tracking, frame, w, h)

    # Detect im sicheren CLIP_CONTEXT
    with _ensure_clip_context(context, clip=clip, allow_area_switch=use_override):
        perform_marker_detection(clip, tracking, float(thr), int(mb), int(mdb))

        # RNA/Depsgraph-Update anstoßen
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        tracks = tracking.tracks
        new_tracks = [t for t in tracks if t.name not in initial_names]

        # Near-Duplicate-Filter (relativ zur Bildbreite)
        rel = float(close_dist_rel) if (close_dist_rel is not None and close_dist_rel > 0.0) else 0.01
        distance_px = max(1, int(w * rel))
        thr2 = float(distance_px * distance_px)

        close_tracks = []
        if existing_positions and new_tracks:
            for tr in new_tracks:
                m = tr.markers.find_frame(frame, exact=True)
                if m and not m.mute:
                    x = m.co[0] * w; y = m.co[1] * h
                    for ex, ey in existing_positions:
                        dx = x - ex; dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(tr)
                            break

        # nahe/doppelte Tracks sicher löschen
        if close_tracks:
            deleted_nd = _delete_tracks_hard(tracking, close_tracks)
            if deleted_nd:
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except Exception:
                    pass

        # finale neue Tracks nach Cleanup
        close_set = set(close_tracks)
        cleaned_tracks = [t for t in new_tracks if t not in close_set]
        anzahl_neu = len(cleaned_tracks)

        # Zielkorridor prüfen → End-of-Attempt Cleanup bei Fehlversuch
        if anzahl_neu < int(mn) or anzahl_neu > int(mx):
            # exakt wie Operator: nur die bereinigten neuen Tracks dieses Versuchs löschen
            deleted_fail = _delete_tracks_hard(tracking, cleaned_tracks)
            # Threshold proportional zur Abweichung anpassen
            safe_adapt = max(int(adapt), 1)
            new_thr = max(float(thr) * ((anzahl_neu + 0.1) / float(safe_adapt)), 1e-4)
            scene["last_detection_threshold"] = float(new_thr)

            print(
                f"[Detect] RUNNING: new={anzahl_neu}, mn={mn}, mx={mx}, "
                f"next_thr={new_thr:.6f}, frame={frame}, fail_deleted={deleted_fail}"
            )
            return {"status": "RUNNING", "new_tracks": anzahl_neu, "threshold": float(new_thr), "frame": frame}

        # Erfolg – final erzeugte Tracks für nächsten Run merken (inter-run cleanup)
        try:
            scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
        except Exception:
            scene["detect_prev_names"] = []

    # Erfolg: Threshold persistieren
    scene["last_detection_threshold"] = float(thr)

    # Optionaler Handoff
    if handoff_to_pipeline:
        scene["detect_status"] = "success"
        scene["pipeline_do_not_start"] = False
    else:
        scene["detect_status"] = "standalone_success"
        scene["pipeline_do_not_start"] = True

    print(f"[Detect] READY: new={anzahl_neu}, thr={thr:.6f}, frame={frame}")
    return {"status": "READY", "new_tracks": anzahl_neu, "threshold": float(thr), "frame": frame}


def run_detect_adaptive(context, **kwargs):
    """
    Wiederholt run_detect_once() bis Erfolg oder max_attempts.
    Rückgabe ist das Ergebnis von run_detect_once().
    """
    max_attempts = int(kwargs.pop("max_attempts", 20))
    attempt = 0
    last = None
    while attempt < max_attempts:
        last = run_detect_once(context, **kwargs)
        status = last.get("status")
        if status == "READY":
            return last
        attempt += 1
        if status == "RUNNING":
            lt = last.get("threshold")
            if lt is not None:
                kwargs["detection_threshold"] = float(lt)
        else:
            break
    return last if last else {"status": "FAILED", "reason": "no_attempt"}
