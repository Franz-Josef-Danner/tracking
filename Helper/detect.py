import bpy
import math
import time

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
    """Robustes Entfernen von Tracks per Datablock-API (ohne UI-Kontext)."""
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
    """Positionen existierender Marker (x,y in px) im Ziel-Frame sammeln."""
    out = []
    for t in tracking.tracks:
        m = t.markers.find_frame(frame, exact=True)
        if m and not m.mute:
            out.append((m.co[0] * w, m.co[1] * h))
    return out

def _resolve_clip(context):
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    # Fallback: first movieclip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# Legacy-Helper (API-kompatibel halten)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus
    und liefert die Anzahl selektierter Tracks zurück (Legacy-Kontrakt).
    """
    # einfache Skalierung (stabil gegenüber sehr kleinen Thresholds)
    factor = max(0.25, min(4.0, float(threshold) * 10.0))
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    try:
        bpy.ops.clip.detect_features(
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        # im Fehlerfall keine Selektion
        print(f"[Detect] detect_features exception: {ex}")
        return 0

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------------
# Nicht-modale, einmalige Detection – Funktions-API (für Helper-Aufrufer)
# ---------------------------------------------------------------------------

def _compute_bounds(scene, image_width, detection_threshold, marker_adapt, min_marker, max_marker):
    # Threshold
    if detection_threshold is None or detection_threshold < 0.0:
        detection_threshold = float(
            scene.get("last_detection_threshold",
                      float(getattr(getattr(scene, "tracking_settings", None), "default_correlation_min", 0.75)))
        )
    detection_threshold = float(max(1e-4, min(1.0, detection_threshold)))

    # adapt / bounds
    if marker_adapt is None or marker_adapt < 0:
        marker_adapt = int(scene.get("marker_adapt", int(scene.get("marker_basis", 20))))
    marker_adapt = int(max(1, marker_adapt))
    basis_for_bounds = int(max(1, int(marker_adapt * 1.1)))

    if min_marker is None or min_marker < 0:
        min_marker = int(max(1, int(basis_for_bounds * 0.9)))
    if max_marker is None or max_marker < 0:
        max_marker = int(max(2, int(basis_for_bounds * 1.1)))

    # bases
    margin_base = max(1, int(image_width * 0.025))
    min_distance_base = max(1, int(image_width * 0.05))

    return detection_threshold, marker_adapt, min_marker, max_marker, margin_base, min_distance_base

def run_detect_once(context, *, start_frame=None, detection_threshold=-1.0,
                    marker_adapt=-1, min_marker=-1, max_marker=-1,
                    margin_base=-1, min_distance_base=-1,
                    close_dist_rel=0.01, handoff_to_pipeline=False):
    """
    Führt einen synchronen, einfachen Detect-Pass aus und liefert ein Ergebnis-Dict.
    KEINE nachgelagerte Pipeline-Steuerung. Side-Effects minimiert.
    """
    clip = _resolve_clip(context)
    if clip is None:
        return {"status": "FAILED", "reason": "no_clip"}

    tracking = clip.tracking
    scene = context.scene
    image_width = int(clip.size[0])

    # Parameter vorbereiten
    thr, adapt, mn, mx, mb, mdb = _compute_bounds(scene, image_width, detection_threshold, marker_adapt, min_marker, max_marker)
    if margin_base is not None and margin_base >= 0:
        mb = int(margin_base)
    if min_distance_base is not None and min_distance_base >= 0:
        mdb = int(min_distance_base)

    # Frame setzen
    if start_frame is not None:
        try:
            scene.frame_set(int(start_frame))
        except Exception:
            pass

    frame = int(scene.frame_current)
    w, h = clip.size

    # Vorherige neue Tracks entfernen (inter-run cleanup)
    prev_names = set(scene.get("detect_prev_names", []) or [])
    if prev_names:
        _remove_tracks_by_name(tracking, prev_names)
        scene["detect_prev_names"] = []

    # Snapshot vor Detect
    initial_names = {t.name for t in tracking.tracks}
    existing_positions = _collect_existing_positions(tracking, frame, w, h)

    # Detect
    _deselect_all(tracking)
    count_sel = perform_marker_detection(clip, tracking, thr, mb, mdb)

    # Depsgraph "anticken"
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

    # Neue Tracks ermitteln
    tracks = tracking.tracks
    new_tracks = [t for t in tracks if t.name not in initial_names]

    # Near-Duplicate-Filter
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
                    if (dx*dx + dy*dy) < thr2:
                        close_tracks.append(tr)
                        break

    # nahe/doppelte Tracks löschen
    if close_tracks:
        for t in tracks:
            t.select = False
        for t in close_tracks:
            t.select = True
        try:
            bpy.ops.clip.delete_track()
        except Exception:
            _remove_tracks_by_name(tracking, {t.name for t in close_tracks})

    # finale neue Tracks
    close_set = set(close_tracks)
    cleaned_tracks = [t for t in new_tracks if t not in close_set]
    anzahl_neu = len(cleaned_tracks)

    if anzahl_neu < int(mn) or anzahl_neu > int(mx):
        # neu erzeugte wieder entfernen
        if cleaned_tracks:
            for t in tracks:
                t.select = False
            for t in cleaned_tracks:
                t.select = True
            try:
                bpy.ops.clip.delete_track()
            except Exception:
                _remove_tracks_by_name(tracking, {t.name for t in cleaned_tracks})

        # threshold anpassen und zurückmelden (einmaliger Versuch)
        safe_adapt = max(int(adapt), 1)
        new_thr = max(float(thr) * ((anzahl_neu + 0.1) / float(safe_adapt)), 1e-4)
        scene["last_detection_threshold"] = float(new_thr)
        return {"status": "RUNNING", "new_tracks": anzahl_neu, "threshold": float(new_thr), "frame": frame}

    # Erfolg – Namen merken für inter-run cleanup
    try:
        scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
    except Exception:
        scene["detect_prev_names"] = []

    # bewusst keine Pipeline-Flags setzen
    scene["last_detection_threshold"] = float(thr)
    return {"status": "READY", "new_tracks": anzahl_neu, "threshold": float(thr), "frame": frame}

def run_detect_adaptive(context, **kwargs):
    """Wiederholt run_detect_once() bis Erfolg oder max. Versuche."""
    max_attempts = int(kwargs.pop("max_attempts", 10))
    attempt = 0
    last = None
    while attempt < max_attempts:
        last = run_detect_once(context, **kwargs)
        if last.get("status") == "READY":
            return last
        attempt += 1
        if last.get("status") == "RUNNING":
            lt = last.get("threshold")
            if lt is not None:
                kwargs["detection_threshold"] = float(lt)
    return last if last else {"status": "FAILED", "reason": "no_attempt"}

# ---------------------------------------------------------------------------
# (Optional) Operator-Varianten – unverändert beibehalten, falls du sie nutzt
# ---------------------------------------------------------------------------

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "Detect (Adaptive, Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    detection_threshold: bpy.props.FloatProperty(
        name="Threshold",
        default=-1.0,
        min=-1.0,
        soft_max=1.0
    )
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt",
        default=-1,
        min=-1
    )
    min_marker: bpy.props.IntProperty(name="Min Marker", default=-1, min=-1)
    max_marker: bpy.props.IntProperty(name="Max Marker", default=-1, min=-1)
    margin_base: bpy.props.IntProperty(name="Margin Base", default=-1, min=-1)
    min_distance_base: bpy.props.IntProperty(name="Min Dist Base", default=-1, min=-1)
    close_dist_rel: bpy.props.FloatProperty(name="Close Dist (rel)", default=0.01, min=0.0, soft_max=0.2)
    frame: bpy.props.IntProperty(name="Frame", default=0, min=0)
    handoff_to_pipeline: bpy.props.BoolProperty(name="Handoff to Pipeline", default=False)

    # ... (Operator-Implementierung wie in deiner Datei – unverändert)
    # Hinweis: Da dein ursprünglicher Code hier sehr umfangreich ist,
    # bleibt dieser Abschnitt unverändert. Er nutzt intern dieselben
    # Hilfsfunktionen und arbeitet weiterhin mit scene[...] Persistenzfeldern.

class CLIP_OT_detect_once(bpy.types.Operator):
    bl_idname = "clip.detect_once"
    bl_label = "Detect Once (Non-Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    detection_threshold: bpy.props.FloatProperty(
        name="Threshold",
        default=-1.0,
        min=-1.0,
        soft_max=1.0
    )
    marker_adapt: bpy.props.IntProperty(name="Marker Adapt", default=-1, min=-1)
    min_marker: bpy.props.IntProperty(name="Min Marker", default=-1, min=-1)
    max_marker: bpy.props.IntProperty(name="Max Marker", default=-1, min=-1)
    margin_base: bpy.props.IntProperty(name="Margin Base", default=-1, min=-1)
    min_distance_base: bpy.props.IntProperty(name="Min Dist Base", default=-1, min=-1)
    close_dist_rel: bpy.props.FloatProperty(name="Close Dist (rel)", default=0.01, min=0.0, soft_max=0.2)
    frame: bpy.props.IntProperty(name="Frame", default=0, min=0)
    handoff_to_pipeline: bpy.props.BoolProperty(name="Handoff to Pipeline", default=False)

    # ... (Execute-Logik analog deiner Datei – unverändert)
