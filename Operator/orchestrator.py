from __future__ import annotations
from typing import Any, Dict

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
)
from ..Helper.motion_model import cluster_fit_models, select_apply_motion_models
from ..Helper.cleanup_pass import periodic_cleanup


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
        schedule_param_changes(roi_id, tel, frame=f)

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
            except Exception:
                pass

        # Cleanup alle 30 Frames (leichte Defaults)
        if i > 0 and i % 30 == 0:
            try:
                periodic_cleanup(roi_id, clean_error_px=2.0, min_len=5)
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

    # Startparameter
    pattern, alpha, search = init_pattern_search(width, height, motion_score=motion)

    # Channel-Selektion (kurz)
    channel = select_channel(roi_id, pattern, alpha)

    # Detect-Profil via Wrapper
    profile = autotune_detect(roi_id, roi_info={"texture": texture, "motion": motion}, kpis={"texture": texture})

    # Szene-Paket für Seeding
    scene_pkg: Dict[str, Any] = {
        "detect_profile": profile,
        "channel": channel,
        "existing_markers": [],
        "context": context,
        "clip": clip,
        "search": search,
    }

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

    # Peer-Refresh Hook (leichtgewichtig)
    try:
        peer_snap_and_refresh(roi_id)
    except Exception:
        pass

    # Online-Loop (Schrittlänge aus Szene, Default 25)
    steps = int(getattr(scn, "frames_track", 25)) if scn else 25
    online = _run_online_loop(context, roi_id, steps=steps, slice_ms=10)

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
        "metrics": finalize_metrics(),
    }
    return result
