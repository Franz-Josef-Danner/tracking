# /5-Stufen-Setzung inkl. Dedup & Mengensteuerung
from __future__ import annotations
from typing import Dict, List
import time
import numpy as np
import cv2

from .dedup import build_index, keep_if_far_enough, feedback_min_distance
from .micro_validate import validate_markers, trim_to_band
from .init_params import enforce_limits, _round_even


def marker_stage_budget(scene) -> dict:
    """Berechne das /5-Markerbudget aus Gesamtziel und Liefere Stage-Band.
    Input: scene dict mit optionalen Schlüsseln {total_target, marker_stage_lo/hi}.
    Output: {per_stage, lo, hi}
    """
    try:
        total_target = int((scene or {}).get("total_target", 0))
    except Exception:
        total_target = 0
    per_stage = max(0, int(total_target // 5))
    lo = int((scene or {}).get("marker_stage_lo", round(per_stage * 0.9)))
    hi = int((scene or {}).get("marker_stage_hi", round(per_stage * 1.1)))
    return {"per_stage": int(per_stage), "lo": int(lo), "hi": int(hi)}


def _clip_size(clip) -> tuple[int, int]:
    try:
        w, h = getattr(clip, "size", (0, 0))
        return int(w or 0), int(h or 0)
    except Exception:
        return 0, 0


def _coerce_float(val, default: float) -> float:
    try:
        if val is None:
            return float(default)
        return float(val)
    except Exception:
        return float(default)


def _coerce_int(val, default: int) -> int:
    try:
        if val is None:
            return int(default)
        return int(val)
    except Exception:
        return int(default)


def _apply_marker_areas(marker, width: int, height: int, pattern_px: int | None, search_px: int | None) -> None:
    """Setze pattern_corners und search_min/max relativ zur Markerposition.
    Blender erwartet Offsets relativ zur Markerposition in normierten Koordinaten (0..1).
    """
    try:
        if marker is None or width <= 0 or height <= 0:
            return
        # Pattern
        if pattern_px is not None and hasattr(marker, "pattern_corners"):
            try:
                dx = float(pattern_px) / (2.0 * float(width))
                dy = float(pattern_px) / (2.0 * float(height))
                corners = ((-dx, -dy), (dx, -dy), (dx, dy), (-dx, dy))
                marker.pattern_corners = corners  # type: ignore[attr-defined]
            except Exception:
                pass
        # Search
        if search_px is not None and hasattr(marker, "search_min") and hasattr(marker, "search_max"):
            try:
                sx = float(search_px) / (2.0 * float(width))
                sy = float(search_px) / (2.0 * float(height))
                marker.search_min = (-sx, -sy)  # type: ignore[attr-defined]
                marker.search_max = (sx, sy)    # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass


def _persist_markers(context, clip, markers: list[dict], roi_id: int | None = None) -> int:
    """Lege für gegebene Pixelpositionen neue Tracks an (normierte Koordinaten).
    Gibt die Anzahl erfolgreich angelegter Tracks zurück.
    Setzt pro Marker (falls vorhanden) pattern/search via tracking.settings Default
    und selektiert Track+Marker. Zusätzlich explizites Setzen von pattern_corners/search.
    Berücksichtigt margin aus den Tracker-Settings, damit Marker nicht außerhalb des trackbaren Bereichs platziert werden.
    """
    try:
        import bpy  # type: ignore
    except Exception:
        return 0
    if not clip or not markers:
        return 0
    try:
        w, h = getattr(clip, "size", (0, 0))
        if not w or not h:
            return 0
        tr_coll = getattr(getattr(clip, "tracking", None), "tracks", None)
        settings = getattr(getattr(clip, "tracking", None), "settings", None)
        # Margin aus den Tracker-Settings lesen, falls vorhanden
        margin = None
        if settings is not None and hasattr(settings, "margin"):
            try:
                margin = int(getattr(settings, "margin", 0))
            except Exception:
                margin = None
        if margin is None or margin <= 0:
            # Fallback wie in marker_helper_main.py
            margin = max(16, int(0.025 * w))
        frame = int(getattr(getattr(context, "scene", None), "frame_current", 1))
        ok = 0
        for i, m in enumerate(markers):
            try:
                # Optional: stage-spezifische Größen anwenden
                p_sz = None
                s_sz = None
                try:
                    if isinstance(m, dict):
                        if m.get("pattern") is not None:
                            p_sz = int(m.get("pattern"))
                        if m.get("search") is not None:
                            s_sz = int(m.get("search"))
                except Exception:
                    p_sz = p_sz if isinstance(p_sz, int) else None
                    s_sz = s_sz if isinstance(s_sz, int) else None
                if settings is not None:
                    if p_sz is not None and hasattr(settings, "default_pattern_size"):
                        try:
                            settings.default_pattern_size = int(p_sz)
                        except Exception:
                            pass
                    if s_sz is not None and hasattr(settings, "default_search_size"):
                        try:
                            settings.default_search_size = int(s_sz)
                        except Exception:
                            pass

                x = float(m.get("x", 0.0))
                y = float(m.get("y", 0.0))
                # Prüfe margin: Marker dürfen nicht näher am Rand als margin liegen
                if x < margin or x > (w - margin) or y < margin or y > (h - margin):
                    continue  # Marker außerhalb des erlaubten Bereichs, überspringen
                co = (max(0.0, min(1.0, x / float(w))), max(0.0, min(1.0, y / float(h))))
                # Direktes Anlegen eines Tracks
                try:
                    # deterministic naming if roi_id provided
                    if roi_id is not None:
                        name = f"roi_{int(roi_id)}_{i:04d}"
                        try:
                            t = tr_coll.new(name=name)
                        except Exception:
                            t = tr_coll.new() if hasattr(tr_coll, "new") else None
                    else:
                        t = tr_coll.new(name=f"KI_{int(x)}_{int(y)}")
                except Exception:
                    t = tr_coll.new() if hasattr(tr_coll, "new") else None
                if t is not None:
                    try:
                        # Marker erzeugen
                        mk = None
                        if hasattr(t.markers, "insert"):
                            mk = t.markers.insert(frame)
                        elif hasattr(t.markers, "new"):
                            mk = t.markers.new(frame)
                        if mk is None:
                            if hasattr(t.markers, "find_frame"):
                                mk = t.markers.find_frame(frame)
                            else:
                                mk = t.markers[-1] if len(t.markers) > 0 else None
                        if mk is not None:
                            mk.co = co
                            # Explizit Pattern/Search setzen, damit Größen im UI sichtbar sind
                            _apply_marker_areas(mk, int(w), int(h), p_sz, s_sz)
                            # Selektion setzen
                            try:
                                t.select = True
                            except Exception:
                                pass
                            try:
                                mk.select = True
                            except Exception:
                                pass
                            # annotate first marker with roi_id
                            try:
                                if roi_id is not None:
                                    try:
                                        mk["roi_id"] = int(roi_id)
                                    except Exception:
                                        try:
                                            setattr(mk, "roi_id", int(roi_id))
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            # Annotate track with roi_id as custom property so providers can map it
                            try:
                                if roi_id is not None:
                                    try:
                                        # Blender custom property
                                        t["roi_id"] = int(roi_id)
                                    except Exception:
                                        try:
                                            setattr(t, "roi_id", int(roi_id))
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            ok += 1
                            continue
                    except Exception:
                        pass
                # Fallback: Operator
                try:
                    bpy.ops.clip.add_marker(location=co, frame=frame)
                    ok += 1
                    continue
                except Exception:
                    pass
            except Exception:
                continue
        return ok
    except Exception:
        return 0


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
        # Wichtig: neu angelegte Tracks wieder entfernen, damit die Szene nicht vollläuft
        try:
            tr_coll = getattr(getattr(clip, "tracking", None), "tracks", None)
            if tr_coll is not None:
                for t in new_tracks:
                    try:
                        tr_coll.remove(t)
                    except Exception:
                        try:
                            # Fallback über Operator (benötigt evtl. gültigen UI-Kontext)
                            t.select = True
                        except Exception:
                            pass
                try:
                    import bpy as _bpy  # type: ignore
                    _bpy.ops.clip.delete_track()
                except Exception:
                    pass
        except Exception:
            pass
        return out
    except Exception:
        return []


def _detect_candidates_opencv(clip, threshold: float, min_distance_px: int, max_features: int, nms_window_px: int, pattern: int | None = None, search_px: int | None = None) -> List[dict]:
    """OpenCV-Fallback: GFTT-Detector auf erstem Frame des Clips (Platzhalter)."""
    # clip muss ein numpy-Array (H x W) oder ein Objekt mit .get_frame() liefern
    try:
        if hasattr(clip, "get_frame"):
            img = clip.get_frame(0)
        elif isinstance(clip, np.ndarray):
            img = clip
        else:
            return []
        if img is None:
            return []
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # GFTT-Parameter
        quality = _coerce_float(threshold, 0.01)
        min_dist = _coerce_int(min_distance_px, 8)
        max_feat = _coerce_int(max_features, 500)
        corners = cv2.goodFeaturesToTrack(img, maxCorners=max_feat, qualityLevel=quality, minDistance=min_dist)
        out = []
        if corners is not None:
            for c in corners:
                x, y = float(c[0][0]), float(c[0][1])
                out.append({"x": x, "y": y, "corr": 1.0})
        return out
    except Exception:
        return []


def _detect_candidates_placeholder(roi_id, threshold: float, *, min_distance_px: int, levels: int, max_features: int, nms_window_px: int, channel: str | None = None, context=None, clip=None, pattern: int | None = None, search_px: int | None = None) -> List[dict]:
    """Platzhalter für echte Detektion. Versucht Blender-Operator zu nutzen; sonst OpenCV-Fallback."""
    # Blender-Integration (wenn verfügbar)
    cands = _detect_candidates_blender(context, clip, threshold, int(min_distance_px), max_features, nms_window_px, pattern=pattern, search_px=search_px)
    if cands:
        return cands
    # OpenCV-Fallback
    cands = _detect_candidates_opencv(clip, threshold, min_distance_px, max_features, nms_window_px, pattern=pattern, search_px=search_px)
    if cands:
        return cands
    return []


def staged_detect_with_dedup(roi_id, pattern: int, alpha: int, total_target: int, scene) -> dict:
    """
    Implementiert 5 Stufen (thr: 1.0→0.0001) mit:
      - Dedup gegen Alt+Acc (min_distance aus feedback)
      - per_stage=scene['marker_stage_target'] ±10% (lo/hi)
      - Micro-Validation (10f)
      - trim/refill nach Band
      - stufenspezifischem (pattern, alpha, search, levels, edge_suppression)
      - Early-Stop bei Zielerfüllung/Abbruchsignal
    Return Summary {placed, stages, time_ms}.
    """
    t0 = time.time()

    per_stage = max(0, int(total_target // 5))
    lo = int(scene.get("marker_stage_lo", round(per_stage * 0.9))) if isinstance(scene, dict) else int(round(per_stage * 0.9))
    hi = int(scene.get("marker_stage_hi", round(per_stage * 1.1))) if isinstance(scene, dict) else int(round(per_stage * 1.1))

    profile = (scene or {}).get("detect_profile", {}) if isinstance(scene, dict) else {}
    thr_stages = [1.0, 0.1, 0.01, 0.001, 0.0001]

    # optionale Blender-Kontexte
    context = (scene or {}).get("context") if isinstance(scene, dict) else None
    clip = (scene or {}).get("clip") if isinstance(scene, dict) else None
    chan = (scene or {}).get("channel") if isinstance(scene, dict) else None
    width, height = _clip_size(clip)

    # Stage-Schedule für (pattern, alpha, levels, edge)
    def stage_params(stage_idx: int, p0: int, a0: int) -> tuple[int, int, int, bool]:
        """Skaliere pattern eher nach oben (bis ~2.6x p0), search gedämpft und gedeckelt.
        Staffelung:
          1: 0.9x p0, α=2
          2: 1.0x p0, α=3
          3: 1.4x p0, α=3
          4: 1.9x p0, α=4
          5: 2.6x p0, α=4
        Search-Berechnung: search = round_even(min(search_cap_px, round(search_scale * pattern)))
          mit search_scale = min(alpha, 3.0) und search_cap_px = cap_frac * minDim (Default 0.08)
        """
        if stage_idx == 1:
            p_raw, a, lv, edge = int(round(p0 * 0.9)), 2, 1, False
        elif stage_idx == 2:
            p_raw, a, lv, edge = int(round(p0 * 1.0)), 3, 1, False
        elif stage_idx == 3:
            p_raw, a, lv, edge = int(round(p0 * 1.4)), 3, 2, False
        elif stage_idx == 4:
            p_raw, a, lv, edge = int(round(p0 * 1.9)), 4, 3, True
        else:
            p_raw, a, lv, edge = int(round(p0 * 2.6)), 4, 3, True
        # pattern/alpha clampen
        p_c, a_c, _s_dummy = enforce_limits(p_raw, a, width, height)
        # search gedämpft und gedeckelt
        min_dim = max(1, min(int(width), int(height)))
        cap_frac = 0.08
        try:
            # optional aus Szene übersteuerbar
            scn = getattr(context, "scene", None)
            if scn is not None:
                cfg = getattr(scn, "search_cap_frac", None)
                if cfg is not None:
                    cap_frac = float(cfg)
        except Exception:
            pass
        search_cap_px = int(round(cap_frac * float(min_dim)))
        search_scale = min(float(a_c), 3.0)
        s_i = _round_even(int(round(min(search_cap_px, search_scale * float(p_c)))))
        return p_c, a_c, s_i, edge

    # Faktoren (Pattern-bezogen)
    nms_factor = _coerce_float(profile.get("nms_window_factor", 1.0), 1.0)
    max_features = _coerce_int(profile.get("max_features", 500), 500)

    accepted: List[dict] = []
    existing = list((scene or {}).get("existing_markers", [])) if isinstance(scene, dict) else []
    index = build_index(existing)
    stages_info: List[Dict] = []

    min_dist: float | None = None
    total_placed = 0
    accepted_final: List[dict] = []

    for i, thr in enumerate(thr_stages, start=1):
        # Early-Stop per Zeitbudget (Callable oder bool)
        if isinstance(scene, dict):
            tb = scene.get("time_budget_hit", False)
            try:
                if callable(tb):
                    if tb():
                        break
                elif bool(tb):
                    break
            except Exception:
                pass

        # Stufen-Parameter ermitteln
        p_i, a_i, search_i, edge_i = stage_params(i, int(pattern), int(alpha))
        levels_i = 1 if i <= 2 else (2 if i == 3 else 3)
        nms_win = int(round(nms_factor * float(p_i)))

        # Start-Min-Dist (Stufe 1 etwas niedriger), sonst alte Distanz in neue Klammern mappen
        lo_clamp = 2.0 * float(p_i)
        hi_clamp = 3.5 * float(p_i)
        if min_dist is None:
            min_dist = max(lo_clamp, min(hi_clamp, 2.3 * float(p_i)))
        else:
            min_dist = max(lo_clamp, min(hi_clamp, float(min_dist)))

        # Dynamische Ziel-Bandbreite je Stufe (Carry-Over)
        rem_total = max(0, int(total_target) - int(total_placed))
        rem_stages = max(1, len(thr_stages) - (i - 1))
        per_i = max(1, rem_total // rem_stages)
        lo_i = int(round(per_i * 0.9))
        hi_i = int(round(per_i * 1.1))
        # Erlaube Überschreiten des globalen hi, falls nötig um Gesamtziel zu treffen
        hi_current = max(int(hi), int(hi_i))

        placed_this = 0

        # Feintuning: Stage-1 Detection-MinDistance = 2.0·p; max_features +25%
        detect_min_px = int(round(2.0 * float(p_i))) if i == 1 else int(round(min_dist))
        max_features_i = int(round(max_features * 1.25)) if i == 1 else int(max_features)

        cands = _detect_candidates_placeholder(
            roi_id=roi_id,
            threshold=thr,
            min_distance_px=detect_min_px,
            levels=levels_i,
            max_features=max_features_i,
            nms_window_px=nms_win,
            channel=chan,
            context=context,
            clip=clip,
            pattern=p_i,
            search_px=search_i,
        )

        kept = []
        for c in cands:
            # Budget-Check auch innerhalb der Kandidaten-Schleife
            if isinstance(scene, dict):
                tb = scene.get("time_budget_hit", False)
                try:
                    if callable(tb):
                        if tb():
                            break
                    elif bool(tb):
                        break
                except Exception:
                    pass
            if keep_if_far_enough(c, index, min_dist):
                # Stage-Parameter an Kandidat annotieren
                c2 = dict(c)
                c2["pattern"] = int(p_i)
                c2["search"] = int(search_i)
                kept.append(c2)
                accepted.append(c2)
                index["points"].append((float(c.get("x", 0.0)), float(c.get("y", 0.0))))
                placed_this += 1
                total_placed += 1
                if placed_this >= hi_current:
                    break

        # Feedback-Update der Distanz für nächste Entscheidungen in dieser/folgenden Stufen
        min_dist = feedback_min_distance(min_dist, placed_this, per_stage, p_i)
        kept = validate_markers(kept, frames=10, corr_min=0.60, jump_guard=True)
        if len(kept) > hi_current:
            kept = trim_to_band(kept, hi_current)
        # final akzeptierte der Stufe sammeln
        accepted_final.extend(kept)

        stages_info.append({
            "stage": i,
            "threshold": thr,
            "attempted": len(cands),
            "kept": len(kept),
            "placed": placed_this,
            "pattern": int(p_i),
            "alpha": int(a_i),
            "search": int(search_i),
            "levels": int(levels_i),
            "edge_suppr": bool(edge_i),
            "detect_min_distance_px": int(detect_min_px),
            "lo_target": int(lo_i),
            "hi_target": int(hi_current),
            "min_distance_px": float(min_dist),
        })

        # Early-Stop-Bedingungen
        if total_placed >= int(total_target):
            break
        if isinstance(scene, dict):
            cov_ok = scene.get("coverage_ok", False)
            try:
                if callable(cov_ok) and cov_ok():
                    break
            except Exception:
                pass
            if not callable(cov_ok) and bool(scene.get("coverage_ok", False)):
                break
            # time_budget wird zu Beginn der nächsten Stufe erneut geprüft

    # Refill-Pass, falls nach 5 Stufen das Ziel noch nicht erreicht ist
    if total_placed < int(total_target):
        # Vor dem Refill das Budget prüfen – ggf. überspringen
        if isinstance(scene, dict):
            tb = scene.get("time_budget_hit", False)
            skip_refill = False
            try:
                if callable(tb):
                    skip_refill = bool(tb())
                elif bool(tb):
                    skip_refill = True
            except Exception:
                skip_refill = False
            if skip_refill:
                stages_info.append({
                    "stage": 6,
                    "skipped": "time_budget",
                    "threshold": thr_stages[-1],
                })
                # Keine weitere Arbeit, gebe bisherigen Stand zurück
                summary = {
                    "placed": len(accepted_final),
                    "persisted": 0,
                    "stages": stages_info,
                    "time_ms": int(round((time.time() - t0) * 1000.0)),
                }
                return summary

        remaining = int(total_target) - int(total_placed)
        # Nutze letzte Stufen-Parameter (konservativ): p, search, levels=3, edge=True, thr=letzte
        p_r, a_r, search_r, _edge_r = stage_params(5, int(pattern), int(alpha))
        detect_min_px_r = int(round(max(2.0 * float(p_r), min_dist or (2.3 * float(p_r)))))
        nms_win_r = int(round(nms_factor * float(p_r)))
        cands = _detect_candidates_placeholder(
            roi_id=roi_id,
            threshold=thr_stages[-1],
            min_distance_px=detect_min_px_r,
            levels=3,
            max_features=int(max_features * 1.25),
            nms_window_px=nms_win_r,
            channel=chan,
            context=context,
            clip=clip,
            pattern=p_r,
            search_px=search_r,
        )
        placed_refill = 0
        kept = []
        for c in cands:
            # Budget-Check innerhalb Refill-Kandidaten
            if isinstance(scene, dict):
                tb = scene.get("time_budget_hit", False)
                try:
                    if callable(tb):
                        if tb():
                            break
                    elif bool(tb):
                        break
                except Exception:
                    pass
            if keep_if_far_enough(c, index, min_dist):
                c2 = dict(c)
                c2["pattern"] = int(p_r)
                c2["search"] = int(search_r)
                kept.append(c2)
                accepted.append(c2)
                index["points"].append((float(c.get("x", 0.0)), float(c.get("y", 0.0))))
                placed_refill += 1
                total_placed += 1
                if total_placed >= int(total_target):
                    break
        min_dist = feedback_min_distance(min_dist, placed_refill, remaining, p_r)
        kept = validate_markers(kept, frames=10, corr_min=0.60, jump_guard=True)
        accepted_final.extend(kept)
        stages_info.append({
            "stage": 6,
            "threshold": thr_stages[-1],
            "attempted": len(cands),
            "kept": len(kept),
            "placed": placed_refill,
            "pattern": int(p_r),
            "alpha": int(a_r),
            "search": int(search_r),
            "levels": 3,
            "edge_suppr": True,
            "detect_min_distance_px": int(detect_min_px_r),
            "lo_target": 0,
            "hi_target": int(remaining),
            "min_distance_px": float(min_dist),
            "refill": True,
        })

    # Final-Trim auf exaktes Gesamtziel, wenn zu viel
    if len(accepted_final) > int(total_target):
        accepted_final = trim_to_band(accepted_final, int(total_target))

    # Persistiere final akzeptierte Marker als Tracks
    persisted = _persist_markers(context, clip, accepted_final, roi_id=roi_id)

    # Try to register persisted markers into online scope so they are visible to the online loop
    try:
        from .tracking_online import register_persisted_markers
        # Attempt to assemble marker refs: if running inside Blender, try to collect names
        marker_refs = []
        try:
            import bpy  # type: ignore
            tr_coll = getattr(getattr(clip, "tracking", None), "tracks", None)
            if tr_coll is not None:
                # collect last `persisted` tracks by name (best-effort)
                try:
                    for t in list(tr_coll)[-int(persisted) :]:
                        try:
                            marker_refs.append(getattr(t, "name", str(t)))
                        except Exception:
                            continue
                except Exception:
                    marker_refs = []
            else:
                marker_refs = []
        except Exception:
            # Not in Blender or clip not available — leave marker_refs empty
            marker_refs = []

        # If persisted count is zero but there are tracks in the clip with the expected naming
        # pattern, attempt to register those as a fallback so online loop can bind to them.
        if int(persisted or 0) == 0:
            try:
                if marker_refs:
                    # nothing to do, we already collected some names
                    pass
                else:
                    try:
                        import bpy  # type: ignore
                        tr_coll = getattr(getattr(clip, "tracking", None), "tracks", None)
                        if tr_coll is not None:
                            fallback_refs = []
                            roi_id_local = int((scene or {}).get("roi_id", 0) or 0)
                            needle = f"roi_{roi_id_local}_"
                            for t in list(tr_coll):
                                try:
                                    nm = getattr(t, "name", "") or ""
                                    if needle in nm or nm.startswith(needle):
                                        fallback_refs.append(nm)
                                except Exception:
                                    continue
                            if fallback_refs:
                                marker_refs = list(dict.fromkeys(fallback_refs))
                                # update persisted to reflect these discovered tracks (diagnostic only)
                                persisted = len(marker_refs)
                                try:
                                    from .telemetry import log_batch
                                    log_batch("online.bind", "fallback_register_persisted_markers", {"roi_id": int((scene or {}).get("roi_id", 0) or 0), "found": len(marker_refs), "examples": marker_refs[:10]})
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            register_persisted_markers(int((scene or {}).get("roi_id", 0)), marker_refs or [])
        except Exception:
            # If roi_id unknown, fallback to 0
            try:
                register_persisted_markers(0, marker_refs or [])
            except Exception:
                pass
    except Exception:
        pass

    summary = {
        "placed": len(accepted_final),
        "persisted": int(persisted),
        "stages": stages_info,
        "time_ms": int(round((time.time() - t0) * 1000.0)),
    }
    return summary