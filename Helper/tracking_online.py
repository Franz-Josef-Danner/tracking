# Frameweise α-Adjust + gated Pattern-Wechsel (apply-next)
from __future__ import annotations
from typing import Dict, Any, Optional, List
from .metrics_provider import get_metrics_provider, TrackingMetrics
import time
import statistics

# einfacher In-Memory-Zustand je ROI/Marker
_STATE: Dict[int, Dict[str, Any]] = {}


def _roi_state(roi_id: int) -> Dict[str, Any]:
    s = _STATE.setdefault(int(roi_id), {
        "markers": {},
        "scheduled": [],
        "last_any_change_frame": -10**9,
        "last_alpha_change_frame": -10**9,
        "last_pattern_change_frame": -10**9,
        "alpha": 3,
        "pattern": 25,
        "frame": -1,
        "erosion_counter": 0,
        # Rolling Window der letzten Frames für Trigger
        "window": [],  # List[dict] je Frame: {corr, runtime_ms, lost_rate, jump_px, scale_delta, rot_delta}
        # Microcheck-State nach Pattern-Move
        "microcheck": None,  # {active, start_frame, window, prev_pattern, baseline_corr, corr_hist}
        # Letzte Telemetrie (einfach)
        "last_tel": {},
        # Sequence-Tracking Status
        "sequence_ready": False,
        "last_sequence_start": None,
        "retrack_from": None,
    })
    return s


def set_initial_params(roi_id: int, *, pattern: Optional[int] = None, alpha: Optional[int] = None, frame: Optional[int] = None) -> None:
    """Setze Startwerte für Online-Tracking-Zustand (z. B. nach Seeding)."""
    s = _roi_state(int(roi_id))
    if pattern is not None:
        try:
            p = int(pattern)
            s["pattern"] = max(9, min(161, p))
        except Exception:
            pass
    if alpha is not None:
        try:
            a = int(alpha)
            s["alpha"] = max(2, min(4, a))
        except Exception:
            pass
    if frame is not None:
        try:
            s["frame"] = int(frame)
        except Exception:
            pass


def track_one_frame(roi_id, frame: Optional[int] = None) -> dict:
    """1-Step-Tracking Telemetrie; ruft KEIN Blender-Tracking mehr auf.

    Sequence-Tracking wird separat über run_sequence_track(…) ausgelöst.
    Fällt auf synthetische KPIs zurück, wenn keine echten Messwerte verfügbar sind.
    """
    s = _roi_state(int(roi_id))
    if frame is None:
        s["frame"] = int(s.get("frame", -1)) + 1
    else:
        s["frame"] = int(frame)

    provider = get_metrics_provider()
    m: TrackingMetrics = provider.fetch_tracking_metrics(str(roi_id), int(s["frame"]))
    corr = float(m["corr"])
    runtime = float(m["time_ms"])
    lost_rate = 1.0 if m["lost"] else 0.0
    jump_px = float(m["jump_px"])
    scale_delta = float(m["scale_delta"])
    rot_delta = float(m["rot_delta"])
    n = len(s.get("markers", {}))
    tel = {
        "frame": int(s["frame"]),
        "alpha": int(s.get("alpha", 3)),
        "pattern": int(s.get("pattern", 25)),
        "aggregate": {
            "survival_1f": float(1.0 - lost_rate),
            "corr_med_1f": float(corr),
            "runtime_ms": float(runtime),
        },
        "per_marker": [],
        "markers": n,
        "mismatch_rate": 0.0,
        "corr_med": float(corr),
        "runtime_ms": float(runtime),
        "lost_rate": float(lost_rate),
        "jump_px": float(jump_px),
        "scale_delta": float(scale_delta),
        "rot_delta": float(rot_delta),
    }

    s.setdefault("window", [])
    s["window"].append({
        "corr": tel["corr_med"],
        "runtime_ms": tel["runtime_ms"],
        "lost_rate": tel["lost_rate"],
        "jump_px": tel["jump_px"],
        "scale_delta": tel["scale_delta"],
        "rot_delta": tel["rot_delta"],
        "frame": int(s["frame"]),
    })
    if len(s["window"]) > 10:
        s["window"] = s["window"][-10:]

    s["last_tel"] = dict({**tel, "corr_med": tel["aggregate"]["corr_med_1f"]})

    # Logging
    try:
        from .telemetry import log_batch
        log_batch("online.frame", "track_step", {"roi_id": int(roi_id), **{k: v for k, v in tel.items() if k not in ("per_marker",)}})
    except Exception:
        pass

    return tel


def _allow_move(s: Dict[str, Any], now_f: int, min_gap: int, last_key: str) -> bool:
    last = int(s.get(last_key, -10**9))
    any_last = int(s.get("last_any_change_frame", -10**9))
    return (now_f - last) >= min_gap and (now_f - any_last) >= 10


def detect_triggers(roi_id, window: int = 10) -> Dict[str, Any]:
    """Leite Trigger je ROI aus rollierendem Fenster ab, inkl. Hysterese-Zählern.
    Output: {abriss, corr_crash, erosion, stabil_teuer, divergence_high, hyst: {...}}
    """
    s = _roi_state(int(roi_id))
    W: List[Dict[str, Any]] = list(s.get("window", []))[-int(max(1, window)) :]
    if not W:
        return {"abriss": False, "corr_crash": False, "erosion": False, "stabil_teuer": False, "divergence_high": False, "hyst": {}}

    corr_vals = [float(w.get("corr", 0.0)) for w in W]
    runtime_vals = [float(w.get("runtime_ms", 0.0)) for w in W]
    lost_vals = [float(w.get("lost_rate", 0.0)) for w in W]
    jump_vals = [float(w.get("jump_px", 0.0)) for w in W]
    scale_vals = [float(w.get("scale_delta", 0.0)) for w in W]
    rot_vals = [float(w.get("rot_delta", 0.0)) for w in W]

    corr_med = statistics.median(corr_vals) if corr_vals else 0.0
    corr_min = min(corr_vals) if corr_vals else 1.0
    runtime_med = statistics.median(runtime_vals) if runtime_vals else 0.0
    lost_max = max(lost_vals) if lost_vals else 0.0
    jump_med = statistics.median(jump_vals) if jump_vals else 0.0
    scale_med = statistics.median(scale_vals) if scale_vals else 0.0
    rot_med = statistics.median(rot_vals) if rot_vals else 0.0

    # Hysterese-Zähler
    hyst = s.setdefault("hyst", {"erosion": 0, "crash": 0, "div": 0})
    # Definitionen (konservativ)
    erosion_now = 0.7 <= corr_med <= 0.8
    crash_now = corr_min < 0.55 or lost_max > 0.3
    div_now = abs(scale_med) > 0.02 or abs(rot_med) > 0.5 or jump_med > 2.0

    hyst["erosion"] = hyst.get("erosion", 0) + 1 if erosion_now else 0
    hyst["crash"] = hyst.get("crash", 0) + 1 if crash_now else 0
    hyst["div"] = hyst.get("div", 0) + 1 if div_now else 0

    stabil = corr_med > 0.82 and lost_max < 0.05
    teuer = runtime_med > 2.0

    triggers = {
        "abriss": hyst["crash"] >= 1,
        "corr_crash": crash_now,
        "erosion": hyst["erosion"] >= 3,
        "stabil_teuer": bool(stabil and teuer),
        "divergence_high": hyst["div"] >= 2,
        "hyst": dict(hyst),
        "corr_med": corr_med,
        "runtime_med": runtime_med,
    }

    try:
        from .telemetry import log_batch
        log_batch("online.trigger", "detect_triggers", {"roi_id": int(roi_id), **triggers})
    except Exception:
        pass

    return triggers


def schedule_param_changes(roi_id, telemetry: dict, frame: Optional[int] = None, triggers: Optional[Dict[str, Any]] = None) -> None | Dict[str, Any]:
    """Pro Marker: α-Adjust (cheap) live; Pattern-Change gated (apply-next).

    Regeln (vereinfacht):
    - cheap-move α: max 1 Param-Move/10 Frames/Marker
    - gated pattern: Cooldown ≥15 Frames; Trigger bei Erosion (≥3 Frames) oder Divergenz

    Return: ChangePlan (marker-/roi-granular) für t+1 (inkl. evtl. sofort gesetzter α-Änderungen als "applied_now").
    """
    s = _roi_state(int(roi_id))
    corr = float(telemetry.get("corr_med", telemetry.get("aggregate", {}).get("corr_med_1f", 0.8)))
    runtime = float(telemetry.get("runtime_ms", telemetry.get("aggregate", {}).get("runtime_ms", 1.0)))
    now_f = int(telemetry.get("frame", s.get("frame", 0))) if frame is None else int(frame)
    s["frame"] = now_f

    plan: Dict[str, Any] = {"roi_id": int(roi_id), "frame": now_f, "apply_at": now_f + 1, "changes": [], "applied_now": []}

    # Erosionszähler (Legacy)
    if 0.7 <= corr <= 0.8:
        s["erosion_counter"] = int(s.get("erosion_counter", 0)) + 1
    else:
        s["erosion_counter"] = 0

    tr = triggers or detect_triggers(roi_id, window=10)

    # cheap alpha adjust (±1), mit Budget-Gating
    if tr.get("abriss") or corr < 0.65:
        if _allow_move(s, now_f, min_gap=10, last_key="last_alpha_change_frame"):
            s.setdefault("alpha", 3)
            new_a = min(4, int(s["alpha"]) + 1)
            # Sofort setzen (bewusst "cheap"), dennoch in Plan dokumentieren
            s["alpha"] = new_a
            s["last_alpha_change_frame"] = now_f
            s["last_any_change_frame"] = now_f
            plan["applied_now"].append({"type": "alpha", "value": int(new_a)})
    elif tr.get("stabil_teuer") or (corr > 0.8 and runtime > 2.0):
        if _allow_move(s, now_f, min_gap=10, last_key="last_alpha_change_frame"):
            s.setdefault("alpha", 3)
            new_a = max(2, int(s["alpha"]) - 1)
            s["alpha"] = new_a
            s["last_alpha_change_frame"] = now_f
            s["last_any_change_frame"] = now_f
            plan["applied_now"].append({"type": "alpha", "value": int(new_a)})

    # gated pattern adjust (apply-next)
    can_gate = (now_f - int(s.get("last_pattern_change_frame", -10**9)) >= 15)
    erosion_gate = bool(tr.get("erosion")) or (int(s.get("erosion_counter", 0)) >= 3)
    diverge_gate = bool(tr.get("divergence_high"))
    if can_gate and (erosion_gate or diverge_gate):
        s.setdefault("pattern", 25)
        step = 4 if diverge_gate else 2
        next_p = max(9, min(161, int(s["pattern"]) + step))
        if (now_f - int(s.get("last_any_change_frame", -10**9))) >= 10:
            s.setdefault("scheduled", [])
            chg = {"type": "pattern", "value": int(next_p), "apply_at": now_f + 1}
            s["scheduled"].append(chg)
            plan["changes"].append(chg)
            # Reset Erosion-Zähler
            s["erosion_counter"] = 0
            try:
                from .telemetry import log_batch
                log_batch("online.schedule", "pattern", {"roi_id": int(roi_id), "frame": now_f, "to": int(next_p), "reason": "erosion" if erosion_gate else "divergence"})
            except Exception:
                pass

    # Plan-Logging (low-cost)
    try:
        from .telemetry import log_batch
        log_batch("online.schedule", "change_plan", plan)
    except Exception:
        pass

    return plan


def apply_scheduled_next_frame(roi_id, frame: Optional[int] = None) -> None:
    """Pattern-Wechsel mit Re-Template (Medianfenster), Lock & Cooldown.

    Minimal: setzt geplante Änderungen zu Beginn des Frames um.
    """
    s = _roi_state(int(roi_id))
    now_f = int(frame if frame is not None else s.get("frame", 0))
    sch = list(s.get("scheduled", []))
    keep = []
    for ev in sch:
        if int(ev.get("apply_at", now_f + 1)) <= now_f:
            if ev.get("type") == "pattern":
                prev = int(s.get("pattern", 25))
                s["pattern"] = int(ev.get("value", s.get("pattern", 25)))
                s["last_pattern_change_frame"] = now_f
                s["last_any_change_frame"] = now_f
                # Microcheck starten
                s["microcheck"] = {
                    "active": True,
                    "start_frame": now_f,
                    "window": 10,
                    "prev_pattern": int(prev),
                    "baseline_corr": float(s.get("last_tel", {}).get("corr_med", 0.8)),
                    "corr_hist": [],
                }
                # Retrack ab diesem Frame erforderlich
                s["retrack_from"] = now_f
                try:
                    from .telemetry import log_batch
                    log_batch("online.apply", "pattern", {"roi_id": int(roi_id), "frame": now_f, "prev": int(prev), "new": int(s["pattern"])})
                except Exception:
                    pass
        else:
            keep.append(ev)
    s["scheduled"] = keep


def apply_next_frame(roi_id, change_plan: Optional[Dict[str, Any]] = None, frame: Optional[int] = None) -> Dict[str, Any]:
    """Setzt geplante Änderungen in t+1 um und liefert einen ApplyReport zurück.

    - alpha wird direkt gesetzt, sofern im Plan vorhanden
    - pattern-Moves triggern Microcheck & Cooldown (über apply_scheduled_next_frame)
    """
    s = _roi_state(int(roi_id))
    now_f = int(frame if frame is not None else s.get("frame", 0))

    applied, skipped = [], []

    # Übergebenen Plan in die interne Schedule übernehmen (nur zukünftige Events)
    if isinstance(change_plan, dict):
        for ch in change_plan.get("changes", []) or []:
            try:
                ap = int(ch.get("apply_at", now_f + 1))
                if ap <= now_f:
                    # Zu spät – skippe
                    skipped.append({**ch, "reason": "late"})
                    continue
                s.setdefault("scheduled", []).append({**ch, "apply_at": ap})
            except Exception:
                skipped.append({**ch, "reason": "invalid"})
        # alpha-Änderungen sofort anwenden, falls im Plan separat gelistet
        for ch in change_plan.get("applied_now", []) or []:
            if ch.get("type") == "alpha":
                try:
                    s["alpha"] = int(ch.get("value", s.get("alpha", 3)))
                    applied.append({**ch, "apply_at": now_f})
                except Exception:
                    skipped.append({**ch, "reason": "invalid"})

    # Interne Schedule für aktuelles Frame anwenden (pattern etc.)
    before = list(s.get("scheduled", []))
    apply_scheduled_next_frame(roi_id, frame=now_f)
    after = list(s.get("scheduled", []))
    # Erkenne angewendete Events anhand der Differenz
    applied_ids = set(id(x) for x in before) - set(id(x) for x in after)
    for ev in before:
        if id(ev) in applied_ids:
            applied.append({**ev, "apply_at": now_f})

    report = {"applied": applied, "skipped": skipped, "frame": now_f}
    try:
        from .telemetry import log_batch
        log_batch("online.apply", "apply_next_frame", {"roi_id": int(roi_id), **report})
    except Exception:
        pass
    return report


# ———————————— Sequence-Tracking ————————————

def run_sequence_track(roi_id, frame: Optional[int] = None) -> bool:
    """Starte Blender-Tracking mit sequence=True einmalig (oder nach Pattern-Änderung).
    Setzt scene.frame_current optional auf 'frame'.
    """
    s = _roi_state(int(roi_id))
    try:
        import bpy  # type: ignore
        if frame is not None:
            try:
                bpy.context.scene.frame_current = int(frame)
            except Exception:
                pass
        clip = getattr(bpy.context, "edit_movieclip", None)
        if clip is None:
            clip = getattr(getattr(bpy.context, "space_data", None), "clip", None)
        tracks = getattr(getattr(clip, "tracking", None), "tracks", None)
        if tracks is not None:
            try:
                for t in tracks:
                    try:
                        t.select = True
                    except Exception:
                        pass
            except Exception:
                pass
        t0 = time.time()
        try:
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        except Exception:
            return False
        dt_ms = (time.time() - t0) * 1000.0
        s["sequence_ready"] = True
        s["last_sequence_start"] = int(frame) if frame is not None else int(s.get("frame", 0))
        s["retrack_from"] = None
        try:
            from .telemetry import log_batch
            log_batch("online.sequence", "track_markers", {"roi_id": int(roi_id), "frame": int(s.get("last_sequence_start", 0)), "dt_ms": float(dt_ms)})
        except Exception:
            pass
        return True
    except Exception:
        return False


# ———————————— Microcheck & State ————————————

def post_change_microcheck(roi_id, window: int = 10) -> Dict[str, Any]:
    """Verifiziere Wirkung von Pattern-Moves über N Frames; ggf. Rollback.
    Output: {gain_ok: bool|None, delta_corr_med: float|None, frames: int}
    """
    s = _roi_state(int(roi_id))
    mc = s.get("microcheck")
    if not mc or not mc.get("active"):
        return {"gain_ok": None, "delta_corr_med": None, "frames": 0}

    now_f = int(s.get("frame", 0))
    start = int(mc.get("start_frame", now_f))
    win = int(mc.get("window", window))
    # Aktuelle Korr einsammeln
    cur_corr = float(s.get("last_tel", {}).get("corr_med", 0.0))
    mc["corr_hist"].append(cur_corr)

    frames = now_f - start + 1
    if frames < win:
        s["microcheck"] = mc
        return {"gain_ok": None, "delta_corr_med": None, "frames": frames}

    # Auswertung
    baseline = float(mc.get("baseline_corr", 0.0))
    med_corr = statistics.median(mc.get("corr_hist", [cur_corr]))
    delta = float(med_corr - baseline)
    gain_ok = bool(delta >= 0.02)

    # Abschluss: entweder behalten oder Rollback planen
    if not gain_ok:
        prev = int(mc.get("prev_pattern", int(s.get("pattern", 25))))
        s.setdefault("scheduled", []).append({"type": "pattern", "value": prev, "apply_at": now_f + 1})
        try:
            from .telemetry import log_batch
            log_batch("online.microcheck", "rollback", {"roi_id": int(roi_id), "frame": now_f, "delta_corr_med": float(delta), "prev": int(prev), "cur": int(s.get("pattern", 25))})
        except Exception:
            pass
    else:
        try:
            from .telemetry import log_batch
            log_batch("online.microcheck", "gain_ok", {"roi_id": int(roi_id), "frame": now_f, "delta_corr_med": float(delta)})
        except Exception:
            pass

    # Microcheck beenden
    s["microcheck"] = None
    return {"gain_ok": gain_ok, "delta_corr_med": float(delta), "frames": frames}


# ———————————— Convenience ————————————

def get_online_state(roi_id) -> Dict[str, Any]:
    """Gibt eine Kopie des internen Zustands für Debug/UI zurück."""
    s = _roi_state(int(roi_id)).copy()
    # keine Markerlisten leaken (hier Platzhalter leer)
    s.pop("markers", None)
    return s