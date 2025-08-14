# Helper/detect.py
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

def _resolve_clip_from_context(context):
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None


# ---------------------------------------------------------------------------
# Legacy-Helper (API-kompatibel halten)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus
    und liefert die Anzahl selektierter Tracks zurück (Legacy-Kontrakt).
    """
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=float(threshold),
    )
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------------
# Helper – adaptiver Detect, inter-run Cleanup (ehem. modal Operator)
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
    handoff_to_pipeline: bool = False,   # Für Abwärtskompatibilität vorhanden (Verhalten bleibt wie zuvor)
    max_attempts: int = 20,
) -> dict:
    """
    Führt die vormals modale Detect-Logik synchron aus.
    Identische Semantik wie der frühere Operator:
    - adaptive Threshold-Anpassung bis Zielkorridor erreicht
    - inter-run Cleanup via scene['detect_prev_names']
    - setzt scene['detect_status']
    - startet bei Erfolg direkt 'bpy.ops.clip.bidirectional_track'
    """
    scn = context.scene
    scn["detect_status"] = "pending"

    # Guard: kein paralleler Pipeline-Run
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

    # --- Threshold-Start (aus Szene, ggf. überschrieben durch Argument) ---
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

    # Sanity Clamp + Persist
    if not (0.0 < float(detection_threshold) <= 1.0):
        detection_threshold = max(min(float(detection_threshold), 1.0), 1e-4)
    scn["last_detection_threshold"] = float(detection_threshold)
    print(f"[Detect] Start-Threshold={detection_threshold:.6f}")

    # --- marker_adapt / Bounds ---
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

    # --- Bases ---
    margin_base = margin_base if margin_base >= 0 else max(1, int(image_width * 0.025))
    min_distance_base = min_distance_base if min_distance_base >= 0 else max(1, int(image_width * 0.05))

    # --- Frame optional setzen ---
    if frame > 0:
        try:
            scn.frame_set(frame)
        except Exception:
            pass

    # --- Cleanup der Tracks aus dem VORHERIGEN Run ---
    prev_names = set(scn.get("detect_prev_names", []) or [])
    if prev_names:
        _remove_tracks_by_name(tracking, prev_names)
        scn["detect_prev_names"] = []

    attempt = 0
    width, height = clip.size
    # Hauptversuchs-Schleife (statt modalem Timer)
    while attempt < max_attempts:
        current_frame = int(scn.frame_current)

        # Snapshots vor Detect
        tracks = tracking.tracks
        existing_positions = _collect_existing_positions(tracking, current_frame, width, height)
        initial_track_names = {t.name for t in tracks}
        len_before = len(tracks)

        # Detect (Legacy-Helper beibehalten)
        perform_marker_detection(
            clip,
            tracking,
            float(detection_threshold),
            int(margin_base),
            int(min_distance_base),
        )

        # Redraw forcieren, damit RNA/Depsgraph neue Tracks liefern
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        # Warten bis sich die Track-Liste materialisiert (ehem. WAIT-State)
        materialized = False
        for _ in range(50):
            if len(tracking.tracks) != len_before:
                names_now = {t.name for t in tracking.tracks}
                if names_now != initial_track_names:
                    materialized = True
                    break
            time.sleep(0.01)

        # PROCESS-Phase
        tracks = tracking.tracks
        # Neue Tracks dieses Versuchs
        new_tracks = [t for t in tracks if t.name not in initial_track_names]

        # Near-Duplicate-Filter (px, rel. zur Breite)
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

        # Zu nahe neue Tracks löschen – Auswahl danach wiederherstellen
        if close_tracks:
            cleaned_names = {t.name for t in new_tracks if t not in close_tracks}
            _remove_tracks_by_name(tracking, {t.name for t in close_tracks})
            for t in tracking.tracks:
                t.select = (t.name in cleaned_names)

        # Bereinigte neue Tracks
        close_set = set(close_tracks)
        cleaned_tracks = [t for t in new_tracks if t not in close_set]
        anzahl_neu = len(cleaned_tracks)

        # Zielkorridor prüfen
        if anzahl_neu < min_marker or anzahl_neu > max_marker:
            # Alle neu-erzeugten (bereinigten) Tracks dieses Versuchs wieder entfernen
            if cleaned_tracks:
                for t in tracks:
                    t.select = False
                for t in cleaned_tracks:
                    t.select = True
                try:
                    bpy.ops.clip.delete_track()
                except Exception:
                    _remove_tracks_by_name(tracking, {t.name for t in cleaned_tracks})

            # Threshold adaptieren (proportional zur Abweichung vom Ziel)
            safe_adapt = max(adapt, 1)
            detection_threshold = max(
                float(detection_threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            scn["last_detection_threshold"] = float(detection_threshold)
            attempt += 1
            continue  # nächster Versuch

        # Erfolg: final erzeugte Tracks für nächsten Run merken (inter-run cleanup)
        try:
            scn["detect_prev_names"] = [t.name for t in cleaned_tracks]
        except Exception:
            scn["detect_prev_names"] = []

        # --- Handoff: Detect → Tracking (identisch zum Operator) ---
        scn["detect_status"] = "success"
        scn["pipeline_do_not_start"] = False

        # Tracking direkt starten
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

    # Abbruch nach max_attempts
    scn["detect_status"] = "failed"
    return {
        "status": "failed",
        "attempts": attempt,
        "threshold": float(detection_threshold),
    }


# ---------------------------------------------------------------------------
# Alias für Abwärtskompatibilität
# ---------------------------------------------------------------------------

# detect.py
def run_detect_once(context, start_frame=None, **_):
    """
    Shim für alte Aufrufer:
    - Optional auf start_frame springen
    - Dann die eigentliche adaptive Detection starten (ohne unbekannte kwargs)
    Rückgabe: {'FINISHED'}|{'CANCELLED'} analog Operator-Verhalten
    """
    import bpy
    if start_frame is not None:
        try:
            context.scene.frame_current = int(start_frame)
        except Exception:
            pass

    # Falls du perform_marker_detection/run_detect_adaptive hast, hier aufrufen:
    try:
        # Preferierte interne API – passe an deine Datei an:
        # return perform_marker_detection(context)          # Variante 1
        return run_detect_adaptive(context)                 # Variante 2
    except TypeError:
        # Fallback: manche Signaturen heißen 'frame' statt 'start_frame'
        try:
            return run_detect_adaptive(context)
        except Exception as ex:
            print(f"[Detect] run_detect_once failed: {ex}")
            return {'CANCELLED'}
