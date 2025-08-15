# detect_neu.py — robuste Version mit Pre‑Pass‑Cleanup & RUNNING‑Sicherungsanker
# kompatibel zum bestehenden Coordinator
import bpy
import math
from typing import Dict, Any, Optional, List, Tuple

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
]

_LOCK_KEY = "__detect_lock"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


def _remove_tracks_by_name(tracking: bpy.types.MovieTracking, names_to_remove) -> int:
    """Robustes Entfernen von Tracks per Datablock‑API (UI‑Kontext‑frei)."""
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
    """Positionen existierender Marker (x,y in px) im Ziel‑Frame sammeln."""
    out: List[Tuple[float, float]] = []
    for t in tracking.tracks:
        # find_frame: API kann je nach Blender Build exact-Arg verschieden handhaben
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0] * w, m.co[1] * h))
    return out


def _resolve_clip(context) -> Optional[bpy.types.MovieClip]:
    """Clip aus aktivem CLIP_EDITOR bevorzugen, sonst erstes MovieClip‑Datablock."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == "CLIP_EDITOR":
        c = getattr(space, "clip", None)
        if c:
            return c
    for c in bpy.data.movieclips:
        return c
    return None


def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    """
    Skaliert margin/min_distance gemäß Heuristik:
      factor = log10(threshold * 1e6) / 6
    """
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))
    return margin, min_distance


# ---------------------------------------------------------------------------
# Legacy‑Helper (beibehalten)
# ---------------------------------------------------------------------------

def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    """
    Führt detect_features mit skalierten Parametern aus
    und liefert die Anzahl selektierter Tracks zurück (Legacy‑Kontrakt).
    """
    margin, min_distance = _scaled_params(float(threshold), int(margin_base), int(min_distance_base))
    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=float(threshold),
    )
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------------
# EIN einzelner Detect‑Pass (Coordinator‑kompatibel)
# ---------------------------------------------------------------------------

def run_detect_once(
    context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    marker_adapt: Optional[int] = None,
    min_marker: Optional[int] = None,
    max_marker: Optional[int] = None,
    margin_base: Optional[int] = None,        # px; Default: 2.5% Bildbreite
    min_distance_base: Optional[int] = None,  # px; Default: 5% Bildbreite
    close_dist_rel: float = 0.01,             # 1% Bildbreite
) -> Dict[str, Any]:
    """
    Führt GENAU EINEN Detect‑Pass aus und bewertet das Ergebnis.

    Rückgabe:
      {
        "status": "READY" | "RUNNING" | "FAILED",
        "new_tracks": int,
        "threshold": float,
        "frame": int
      }
    """
    scn = context.scene
    scn[_LOCK_KEY] = True  # Lock setzen (FSM wartet, solange True)

    try:
        clip = _resolve_clip(context)
        if not clip:
            return {"status": "FAILED", "reason": "no_clip"}

        tracking = clip.tracking
        settings = tracking.settings
        width, height = int(clip.size[0]), int(clip.size[1])

        # Optional: Frame setzen
        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:
                pass
        frame = int(scn.frame_current)

        # --- PRE‑PASS CLEANUP: entferne Reste aus vorherigen fehlgeschlagenen Versuchen ---
        prev_names = set(scn.get("detect_prev_names", []) or [])
        if prev_names:
            # Datenblock‑basiert, UI‑unabhängig
            _remove_tracks_by_name(tracking, prev_names)
            scn["detect_prev_names"] = []
            try:
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            except Exception:
                pass

        # Start‑Threshold
        if threshold is None:
            threshold = float(
                scn.get(
                    "last_detection_threshold",
                    float(getattr(settings, "default_correlation_min", 0.75)),
                )
            )
        threshold = max(1e-6, float(threshold))

        # Ziel / Bounds
        if marker_adapt is None:
            marker_adapt = int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
        safe_adapt = max(1, int(marker_adapt))

        basis_for_bounds = int(marker_adapt * 1.1) if marker_adapt > 0 else int(scn.get("marker_basis", 20))
        if min_marker is None:
            min_marker = int(max(1, basis_for_bounds * 0.9))
        if max_marker is None:
            max_marker = int(max(2, basis_for_bounds * 1.1))

        # Basen (px)
        if margin_base is None:
            margin_base = max(1, int(width * 0.025))
        if min_distance_base is None:
            min_distance_base = max(1, int(width * 0.05))

        # Snapshot vor Detect
        initial_names = {t.name for t in tracking.tracks}
        existing_px = _collect_existing_positions(tracking, frame, width, height)

        # Detect
        _deselect_all(tracking)
        perform_marker_detection(
            clip,
            tracking,
            float(threshold),
            int(margin_base),
            int(min_distance_base),
        )

        # Redraw erzwingen (RNA/Depsgraph)
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Neue Tracks bestimmen (roh)
        tracks = tracking.tracks
        new_tracks_raw = [t for t in tracks if t.name not in initial_names]
        added_names = {t.name for t in new_tracks_raw}

        # Near‑Duplicate‑Filter
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

        # Zu nahe neue Tracks löschen (best effort)
        if close_tracks:
            _deselect_all(tracking)
            for t in close_tracks:
                t.select = True
            try:
                bpy.ops.clip.delete_track()
            except Exception:
                _remove_tracks_by_name(tracking, {t.name for t in close_tracks})

        # Bereinigte neue Tracks
        close_set = {t.name for t in close_tracks}
        cleaned_tracks = [t for t in new_tracks_raw if t.name not in close_set]
        anzahl_neu = len(cleaned_tracks)

        # ---------------------------
        # Zielkorridor prüfen
        # ---------------------------
        if anzahl_neu < int(min_marker) or anzahl_neu > int(max_marker):
            # *** HARTE GARANTIE: ALLE in diesem Pass erzeugten Tracks entfernen ***
            remaining_after_delete = set()

            if added_names:
                # 1) Operator‑Versuch (UI‑Kontext, falls vorhanden)
                _deselect_all(tracking)
                for t in tracks:
                    if t.name in added_names:
                        t.select = True
                op_deleted = False
                try:
                    bpy.ops.clip.delete_track()
                    op_deleted = True
                except Exception:
                    op_deleted = False

                # 2) Fallback über Datablock‑API (löscht ggf. verbleibende)
                still_there = {t.name for t in tracking.tracks if t.name in added_names}
                if still_there:
                    removed = _remove_tracks_by_name(tracking, still_there)
                    # Prüfen, ob noch etwas übrig blieb (extrem selten)
                    remaining_after_delete = {n for n in still_there if n in {t.name for t in tracking.tracks}}
                else:
                    remaining_after_delete = set()

                # 3) Depsgraph/RNA auffrischen
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:
                    pass

            # Threshold adaptieren (proportional zur Abweichung)
            new_threshold = max(
                float(threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            scn["last_detection_threshold"] = float(new_threshold)

            # *** WICHTIGER SICHERUNGSANKER: ***
            # Wenn trotz aller Versuche noch Reste dieses Passes vorhanden sein könnten,
            # für den nächsten Pass vormerken → garantiertes Aufräumen zu Beginn.
            scn["detect_prev_names"] = list(remaining_after_delete) if remaining_after_delete else []

            return {
                "status": "RUNNING",
                "new_tracks": int(anzahl_neu),
                "threshold": float(new_threshold),
                "frame": int(frame),
            }

        # Erfolg: READY → nichts vormerken (Marker sollen bleiben)
        scn["detect_prev_names"] = []
        scn["last_detection_threshold"] = float(threshold)

        return {
            "status": "READY",
            "new_tracks": int(anzahl_neu),
            "threshold": float(threshold),
            "frame": int(frame),
        }

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}
    finally:
        # Lock freigeben
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Optionaler Mehrfach‑Wrapper (praktisch für manuelle Tests)
# ---------------------------------------------------------------------------

def run_detect_adaptive(
    context,
    *,
    start_frame: Optional[int] = None,
    max_attempts: int = 8,
    **kwargs,
) -> Dict[str, Any]:
    """
    Führt run_detect_once mehrfach aus, bis READY/FAILED oder max_attempts erreicht ist.
    """
    last: Dict[str, Any] = {}
    for _ in range(max_attempts):
        last = run_detect_once(context, start_frame=start_frame, **kwargs)
        if last.get("status") in ("READY", "FAILED"):
            return last
        # RUNNING: nächster Pass (Threshold/Frame werden aus Scene gelesen)
        start_frame = last.get("frame", start_frame)
    return last or {"status": "FAILED", "reason": "max_attempts_exceeded"}
