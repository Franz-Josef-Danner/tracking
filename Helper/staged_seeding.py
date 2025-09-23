# /5-Stufen-Setzung inkl. Dedup & Mengensteuerung
from __future__ import annotations
from typing import Dict, List
import time

from .dedup import build_index, keep_if_far_enough, feedback_min_distance
from .micro_validate import validate_markers, trim_to_band


def _detect_candidates_blender(context, clip, threshold: float, min_distance_px: int, max_features: int, nms_window_px: int, pattern: int | None = None, search_px: int | None = None) -> List[dict]:
    """Versuche Blender-intern Features zu detektieren und liefere Marker-Kandidaten zurück.
    Gibt eine Liste von Dicts mit Pixel-Koordinaten zurück: {'x': px, 'y': px}.
    """
    try:
        import bpy  # type: ignore
    except Exception:
        return []

    try:
        # Tracking Settings behutsam setzen, wenn vorhanden
        ts = getattr(getattr(clip, "tracking", None), "settings", None)
        if ts:
            # Muster-/Suchgröße optional anreichern
            if pattern and hasattr(ts, "default_pattern_size"):
                try:
                    ts.default_pattern_size = int(pattern)
                except Exception:
                    pass
            if search_px and hasattr(ts, "default_search_size"):
                try:
                    ts.default_search_size = int(search_px)
                except Exception:
                    pass

        # Vorher/Nachher-Trackinglisten vergleichen
        tracks_before = list(getattr(getattr(clip, "tracking", None), "tracks", []) or [])
        n_before = len(tracks_before)

        # Operator auf aktuellem Frame ausführen
        frame = int(getattr(getattr(context, "scene", None), "frame_current", 1))
        try:
            bpy.ops.clip.detect_features(threshold=float(threshold), min_distance=int(min_distance_px))
        except Exception:
            # Fallback: evtl. andere Parameternamen – dann ungetan zurück
            return []

        tracks_after = list(getattr(getattr(clip, "tracking", None), "tracks", []) or [])
        n_after = len(tracks_after)
        new_n = max(0, n_after - n_before)
        if new_n <= 0:
            return []

        w, h = (0, 0)
        try:
            w, h = getattr(clip, "size", (0, 0))
        except Exception:
            pass

        # Neue Tracks sind typischerweise am Ende angehängt
        new_tracks = tracks_after[-new_n:]
        out: List[dict] = []
        for t in new_tracks:
            try:
                # Marker am aktuellen Frame holen
                # API: t.markers.find_frame(frame) (falls vorhanden), sonst best-effort
                marker = None
                if hasattr(t.markers, "find_frame"):
                    marker = t.markers.find_frame(frame)
                if marker is None:
                    # Heuristik: nimm den Marker mit passender frame Nummer, sonst letzten
                    marker = None
                    for m in t.markers:
                        if int(getattr(m, "frame", -1)) == frame:
                            marker = m
                            break
                    if marker is None and len(t.markers) > 0:
                        marker = t.markers[-1]
                if marker is None:
                    continue
                co = getattr(marker, "co", None)
                if not co or w == 0 or h == 0:
                    continue
                x = float(co[0]) * float(w)
                y = float(co[1]) * float(h)
                out.append({"x": x, "y": y, "corr": 1.0})
            except Exception:
                continue
        return out
    except Exception:
        return []


def _detect_candidates_placeholder(roi_id, threshold: float, levels: int, max_features: int, nms_window_px: int, channel: str | None = None, *, context=None, clip=None, pattern: int | None = None, search_px: int | None = None) -> List[dict]:
    """Platzhalter für echte Detektion. Versucht Blender-Operator zu nutzen; sonst leer.
    Struktur je Kandidat (Beispiel): {'x': float, 'y': float, 'score': float}
    """
    # Blender-Integration (wenn verfügbar)
    cands = _detect_candidates_blender(context, clip, threshold, nms_window_px if nms_window_px else 0, max_features, nms_window_px, pattern=pattern, search_px=search_px)
    if cands:
        return cands
    # TODO: hier alternativen Detector einhängen (z. B. OpenCV)
    return []


def staged_detect_with_dedup(roi_id, pattern: int, alpha: int, total_target: int, scene) -> dict:
    """
    Implementiert 5 Stufen (thr: 1.0→0.0001) mit:
      - Dedup gegen Alt+Acc (min_distance aus feedback)
      - per_stage=scene['marker_stage_target'] ±10% (lo/hi)
      - Micro-Validation (10f)
      - trim/refill nach Band
    Return Summary {placed, stages, time_ms}.
    """
    t0 = time.time()

    per_stage = max(0, int(total_target // 5))
    lo = int(scene.get("marker_stage_lo", round(per_stage * 0.9))) if isinstance(scene, dict) else int(round(per_stage * 0.9))
    hi = int(scene.get("marker_stage_hi", round(per_stage * 1.1))) if isinstance(scene, dict) else int(round(per_stage * 1.1))

    profile = (scene or {}).get("detect_profile", {}) if isinstance(scene, dict) else {}
    thr_stages = [1.0, 0.1, 0.01, 0.001, 0.0001]

    min_dist = float(profile.get("min_distance_factor", 2.5)) * float(pattern)
    nms_win = int(round(float(profile.get("nms_window_factor", 1.0)) * float(pattern)))
    levels = int(profile.get("levels", 1))
    max_features = int(profile.get("max_features", 500))

    accepted: List[dict] = []
    existing = list((scene or {}).get("existing_markers", [])) if isinstance(scene, dict) else []
    index = build_index(existing)
    stages_info: List[Dict] = []

    # optionale Blender-Kontexte
    context = (scene or {}).get("context") if isinstance(scene, dict) else None
    clip = (scene or {}).get("clip") if isinstance(scene, dict) else None
    search_px = (scene or {}).get("search") if isinstance(scene, dict) else None

    for i, thr in enumerate(thr_stages, start=1):
        placed_this = 0
        cands = _detect_candidates_placeholder(
            roi_id=roi_id,
            threshold=thr,
            levels=levels,
            max_features=max_features,
            nms_window_px=nms_win,
            channel=(scene or {}).get("channel") if isinstance(scene, dict) else None,
            context=context,
            clip=clip,
            pattern=pattern,
            search_px=search_px,
        )

        kept = []
        for c in cands:
            if keep_if_far_enough(c, index, min_dist):
                kept.append(c)
                accepted.append(c)
                index["points"].append((float(c.get("x", 0.0)), float(c.get("y", 0.0))))
                placed_this += 1
                if placed_this >= hi:
                    break

        min_dist = feedback_min_distance(min_dist, placed_this, per_stage, pattern)
        kept = validate_markers(kept, frames=10, corr_min=0.60, jump_guard=True)
        if len(kept) > hi:
            kept = trim_to_band(kept, hi)

        stages_info.append({
            "stage": i,
            "threshold": thr,
            "attempted": len(cands),
            "kept": len(kept),
            "placed": placed_this,
            "min_distance_px": float(min_dist),
        })

        if placed_this >= lo:
            pass

        if isinstance(scene, dict) and scene.get("time_budget_hit", False):
            break

    summary = {
        "placed": len(accepted),
        "stages": stages_info,
        "time_ms": int(round((time.time() - t0) * 1000.0)),
    }
    return summary