from __future__ import annotations
from typing import Any, Dict
import time

from ..Helper.init_params import init_pattern_search
from ..Helper.detect_autotune import autotune_detect
from ..Helper.staged_seeding import staged_detect_with_dedup
from ..Helper.roi import analyze_rois, prioritize_rois
from ..Helper.channels import select_channel
from ..Helper.telemetry import log_step, finalize_metrics
from ..Helper.peer_stabilize import peer_snap_and_refresh
from ..Helper.tracking_online import (
    track_one_frame,
    schedule_param_changes,
    apply_scheduled_next_frame,
    get_online_state,
    set_initial_params,
    detect_triggers,
    post_change_microcheck,
)
from ..Helper.motion_model import cluster_fit_models, select_apply_motion_models
from ..Helper.cleanup_pass import periodic_cleanup
# Neu: Presets & Zielscore
from ..Helper.presets import load_preset, save_preset, write_presets
from ..Helper.telemetry import compute_target_score
# Limits erneut anwenden nach Preset
from ..Helper.init_params import enforce_limits
from ..Helper.telemetry import log_batch


def _clip_size(clip: Any) -> tuple[int, int]:
    try:
        w, h = getattr(clip, "size", (0, 0))
        return int(w or 0), int(h or 0)
    except Exception:
        return 0, 0


def _try_marker_baseline(context) -> None:
    # Setzt sinnvolle Szene-Baselines (optional)
    try:
        from ..Helper.marker_helper_main import marker_helper_main
        marker_helper_main(context)
    except Exception:
        pass


def _run_online_loop(context, roi_id: int, steps: int = 25, slice_ms: int = 10) -> Dict[str, Any]:
    """Führt eine einfache Online-Schleife aus (blocking, minimal)."""
    import time

    agg = {"frames": 0, "moves": 0}
    base_t = time.time()

    # virtuelle Framezählung: starte bei aktuellem Blender-Frame (falls vorhanden)
    try:
        cur = int(getattr(getattr(context, "scene", None), "frame_current", 1))
    except Exception:
        cur = 1

    for i in range(steps):
        f = cur + i
        t0 = time.time()

        # Apply-next zu Beginn des Frames
        apply_scheduled_next_frame(roi_id, frame=f)

        tel = track_one_frame(roi_id, frame=f)
        # Trigger ableiten und loggen
        trig = detect_triggers(roi_id, window=10)
        log_batch("online.frame", "trigger", {"frame": f, "triggers": trig})

        schedule_param_changes(roi_id, tel, frame=f, triggers=trig)

        # Microcheck nach Pattern-Anwendung überwachen
        mc = post_change_microcheck(roi_id, window=10)
        if mc.get("gain_ok") is not None:
            log_batch("online.frame", "microcheck", {"frame": f, **mc})

        # Periodik: alle 20 Frames Modell-Fit/Selektion (Cluster-basiert, Platzhalter)
        if i > 0 and i % 20 == 0:
            fits_pack = cluster_fit_models(roi_id, window=30)
            fits = fits_pack.get("fits", {})
            feats = fits_pack.get("feats", {})
            decisions = select_apply_motion_models(roi_id, fits, feats)
            log_step("online.model_select", {"frame": f, "decisions": decisions})

        # Peer-Refresh alle 5 Frames
        if i % 5 == 0:
            try:
                peer_snap_and_refresh(roi_id)
                log_batch("online.frame", "peer_refresh", {"frame": f})
            except Exception:
                pass

        # Cleanup alle 30 Frames (leichte Defaults)
        if i > 0 and i % 30 == 0:
            try:
                periodic_cleanup(roi_id, clean_error_px=2.0, min_len=5)
                log_batch("online.frame", "cleanup", {"frame": f})
            except Exception:
                pass

        log_step("online.frame", {"frame": f, "tel": tel, "state": get_online_state(roi_id)})

        agg["frames"] += 1

        # Zeit-Slice / ROI – breche ab, wenn Budget überschritten
        dt = (time.time() - t0) * 1000.0
        if dt > slice_ms:
            log_step("online.slice_budget", {"frame": f, "dt_ms": dt, "slice_ms": slice_ms})
            # Frühzeitiger Abbruch der restlichen Aktionen des Frames – wir gehen zum nächsten weiter
            continue

    agg["elapsed_ms"] = int(round((time.time() - base_t) * 1000.0))
    agg["state"] = get_online_state(roi_id)
    return agg


def _bins(v: float, edges: list[float]) -> int:
    for i, e in enumerate(edges):
        if v <= e:
            return i
    return len(edges)


def _roi_signature(clip: Any, roi_info: Dict[str, Any]) -> Dict[str, Any]:
    w, h = _clip_size(clip)
    tex = float(roi_info.get("texture", 0.5) or 0.5)
    mot = float(roi_info.get("motion", 0.5) or 0.5)
    return {
        "resolution": f"{w}x{h}",
        "texture_bin": _bins(tex, [0.25, 0.5, 0.75]),
        "motion_bin": _bins(mot, [0.25, 0.5, 0.75]),
        "quadrant": 0,
    }


def _sanitize_detect_profile(profile: dict | None) -> dict:
    """Erzwinge gültige Typen/Werte, ersetze None durch Defaults."""
    p = dict(profile or {})
    def _coerce(val, default):
        try:
            if isinstance(default, float):
                return float(val)
            if isinstance(default, int):
                return int(val)
            if isinstance(default, bool):
                return bool(val)
            return val if val is not None else default
        except Exception:
            return default
    thr = _coerce(p.get("threshold", None), 1e-3)
    thr = max(1e-5, min(1e-2, float(thr)))
    levels = int(max(1, min(3, _coerce(p.get("levels", None), 1))))
    edge = bool(_coerce(p.get("edge_suppr", None), False))
    maxf = int(max(100, min(5000, _coerce(p.get("max_features", None), 500))))
    mindf = float(max(2.0, min(4.0, _coerce(p.get("min_distance_factor", None), 2.5))))
    nmsf = float(max(0.5, min(2.0, _coerce(p.get("nms_window_factor", None), 1.0))))
    p.update({
        "threshold": float(thr),
        "levels": int(levels),
        "edge_suppr": bool(edge),
        "max_features": int(maxf),
        "min_distance_factor": float(mindf),
        "nms_window_factor": float(nmsf),
    })
    return p


def run_autotrack(context, clip) -> dict:
    """
    Dünne, lauffähige Orchestrierung des Minimalpfads:
      - STRM/ROI-Analyse & Priorisierung (platzhalter)
      - Startwerte (pattern/alpha/search)
      - Channel-Selektion (kurzer Heuristik-Prepass)
      - Detect-Autotune (Wrapper)
      - Gestuftes Seeding mit Dedup/Micro-Validation
      - Online-Frame-Loop mit Budget- und Cooldown-Gating
    Return: einfache Telemetrie/KPIs.
    """
    scn = getattr(context, "scene", None)

    _try_marker_baseline(context)

    width, height = _clip_size(clip)

    # Marker-Ziel ableiten (robust, ohne UI-Abhängigkeit)
    marker_frame = int(getattr(scn, "marker_frame", 25)) if scn else 25
    factor = int(getattr(scn, "marker_factor", 4)) if scn else 4
    total_target = int(max(1, marker_frame * factor))

    # STRM/ROI (Platzhalter): nimm beste ROI
    rois = analyze_rois(clip)
    order = prioritize_rois(rois)
    roi_id = order[0] if order else 0
    r = rois.get(roi_id, {})
    texture = float(r.get("texture", 0.5) or 0.5)
    motion = float(r.get("motion", 0.5) or 0.5)

    # ROI-Signatur + optional Preset laden
    signature = _roi_signature(clip, r)
    clip_id = getattr(clip, "name", "clip") or "clip"
    preset = load_preset(str(clip_id), signature) or {}

    # Startparameter
    pattern, alpha, search = init_pattern_search(width, height, motion_score=motion)

    # Evtl. Preset anwenden (teilweise)
    if isinstance(preset, dict):
        params = preset.get("params", preset)
        pattern = int(params.get("pattern", pattern) or pattern)
        alpha = int(params.get("alpha", alpha) or alpha)
        search = int(params.get("search", search) or search)
    # Nach Preset-Anwendung Grenzwerte sicherstellen
    pattern, alpha, search = enforce_limits(pattern, alpha, width, height)

    # Channel-Selektion (kurz)
    channel = select_channel(roi_id, pattern, alpha)
    if isinstance(preset, dict):
        params = preset.get("params", preset)
        ch = params.get("channel", channel)
        channel = str(ch) if ch else "Y"
    channel = channel or "Y"

    # Detect-Profil via Wrapper
    profile = autotune_detect(roi_id, roi_info={"texture": texture, "motion": motion}, kpis={"texture": texture})
    if isinstance(preset, dict):
        params = preset.get("params", preset)
        # Erlaube Überschreiben einzelner Felder
        p2 = dict(profile)
        for k in ("threshold", "levels", "edge_suppr", "max_features", "min_distance_factor", "nms_window_factor"):
            if k in params:
                p2[k] = params[k]
        profile = p2
    # Profil sanity check
    profile = _sanitize_detect_profile(profile)

    # Zeitbudget für Seeding: nur aktiv, wenn explizit >0 gesetzt
    raw_budget = getattr(scn, "seeding_budget_ms", None) if scn else None
    try:
        seeding_budget_ms = int(raw_budget) if raw_budget is not None else None
    except Exception:
        seeding_budget_ms = None
    budget_fn = None
    if seeding_budget_ms is not None and seeding_budget_ms > 0:
        seeding_t0 = time.time()
        def _time_budget_hit() -> bool:
            return (time.time() - seeding_t0) * 1000.0 >= seeding_budget_ms
        budget_fn = _time_budget_hit

    # Szene-Paket für Seeding
    scene_pkg: Dict[str, Any] = {
        "detect_profile": profile,
        "channel": channel,
        "existing_markers": [],
        "context": context,
        "clip": clip,
        "search": search,
    }
    if budget_fn is not None:
        scene_pkg["time_budget_hit"] = budget_fn

    log_step("orchestrator.pre_seeding", {
        "roi_id": roi_id,
        "clip_size": (width, height),
        "pattern": pattern,
        "alpha": alpha,
        "search": search,
        "channel": channel,
        "detect_profile": profile,
    })

    # Gestufte Setzung ausführen
    summary = staged_detect_with_dedup(
        roi_id=roi_id,
        pattern=pattern,
        alpha=alpha,
        total_target=total_target,
        scene=scene_pkg,
    )

    log_step("orchestrator.post_seeding", summary)

    # Online-Startwerte mit letzter Seeding-Stage synchronisieren
    try:
        stages = summary.get("stages", []) if isinstance(summary, dict) else []
        last = stages[-1] if stages else {}
        p_init = int(last.get("pattern", pattern)) if isinstance(last, dict) else pattern
        a_init = int(last.get("alpha", alpha)) if isinstance(last, dict) else alpha
        set_initial_params(roi_id, pattern=p_init, alpha=a_init)
    except Exception:
        pass

    # Peer-Refresh Hook (leichtgewichtig)
    try:
        peer_snap_and_refresh(roi_id)
    except Exception:
        pass

    # Online-Loop (Schrittlänge aus Szene, Default 25)
    steps = int(getattr(scn, "frames_track", 25)) if scn else 25
    online = _run_online_loop(context, roi_id, steps=steps, slice_ms=10)

    # Einfache KPI-Aggregation und Zielscore
    # Annahmen: survival~1.0 bei erfolgreichen Online-Schritten, corr_med aus letztem Zustand, time_norm aus Laufzeit
    state = online.get("state", {})
    last_corr = float(state.get("corr_med", 0.8)) if isinstance(state, dict) else 0.8
    elapsed = max(1, int(online.get("elapsed_ms", 1)))
    time_norm = min(1.0, elapsed / max(10.0, steps * 5.0))  # grobe Normierung
    kpis = {"survival": 1.0, "corr_med": last_corr, "time_norm": time_norm}
    score = compute_target_score(kpis)

    # Preset speichern (Besten-Logik in Helper.preset)
    save_preset(str(clip_id), signature, {
        "pattern": int(pattern),
        "alpha": int(alpha),
        "search": int(search),
        "channel": str(channel),
        **({} if not isinstance(profile, dict) else profile),
    }, score)
    write_presets()

    # Ergebnis zusammenstellen (Minimal-KPIs)
    result = {
        "roi_count": len(rois),
        "roi_id": roi_id,
        "clip_size": (width, height),
        "pattern": pattern,
        "alpha": alpha,
        "search": search,
        "channel": channel,
        "detect_profile": profile,
        "seeding": summary,
        "online": online,
        "kpis": kpis,
        "score": score,
        "metrics": finalize_metrics(),
    }
    return result
