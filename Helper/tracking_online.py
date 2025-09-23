# Frameweise α-Adjust + gated Pattern-Wechsel (apply-next)
from __future__ import annotations
from typing import Dict, Any, Optional
import time

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
    })
    return s


def track_one_frame(roi_id, frame: Optional[int] = None) -> dict:
    """1-Step-Tracking für alle Marker im ROI; return Telemetrie-Aggregate.

    Placeholder: liefert stabilen Zustand ohne echte Bildverarbeitung.
    """
    s = _roi_state(int(roi_id))
    # Frame-Index fortschreiben
    if frame is None:
        s["frame"] = int(s.get("frame", -1)) + 1
    else:
        s["frame"] = int(frame)
    n = len(s.get("markers", {}))
    tel = {
        "markers": n,
        "mismatch_rate": 0.0,
        "corr_med": 0.8,
        "runtime_ms": 1.0,
        "frame": int(s["frame"]),
        "alpha": int(s.get("alpha", 3)),
        "pattern": int(s.get("pattern", 25)),
    }
    return tel


def _allow_move(s: Dict[str, Any], now_f: int, min_gap: int, last_key: str) -> bool:
    last = int(s.get(last_key, -10**9))
    any_last = int(s.get("last_any_change_frame", -10**9))
    return (now_f - last) >= min_gap and (now_f - any_last) >= 10


def schedule_param_changes(roi_id, telemetry: dict, frame: Optional[int] = None) -> None:
    """Pro Marker: α-Adjust (cheap) live; Pattern-Change gated (apply-next).

    Regeln (vereinfacht):
    - cheap-move α: max 1 Param-Move/10 Frames/Marker
    - gated pattern: Cooldown ≥15 Frames; Trigger bei Erosion (3 Frames 0.7≤corr≤0.8)
    """
    s = _roi_state(int(roi_id))
    corr = float(telemetry.get("corr_med", 0.8))
    runtime = float(telemetry.get("runtime_ms", 1.0))
    now_f = int(telemetry.get("frame", s.get("frame", 0))) if frame is None else int(frame)
    s["frame"] = now_f

    # Erosionszähler (für Pattern-Gating)
    if 0.7 <= corr <= 0.8:
        s["erosion_counter"] = int(s.get("erosion_counter", 0)) + 1
    else:
        s["erosion_counter"] = 0

    # cheap alpha adjust (±1), mit Budget-Gating
    if corr < 0.65:
        if _allow_move(s, now_f, min_gap=10, last_key="last_alpha_change_frame"):
            s.setdefault("alpha", 3)
            s["alpha"] = min(4, int(s["alpha"]) + 1)
            s["last_alpha_change_frame"] = now_f
            s["last_any_change_frame"] = now_f
    elif corr > 0.8 and runtime > 2.0:
        if _allow_move(s, now_f, min_gap=10, last_key="last_alpha_change_frame"):
            s.setdefault("alpha", 3)
            s["alpha"] = max(2, int(s["alpha"]) - 1)
            s["last_alpha_change_frame"] = now_f
            s["last_any_change_frame"] = now_f

    # gated pattern adjust (apply-next)
    # Bedingungen: Cooldown ≥15 Frames, Erosion ≥3 Frames
    can_gate = (now_f - int(s.get("last_pattern_change_frame", -10**9)) >= 15)
    if can_gate and int(s.get("erosion_counter", 0)) >= 3:
        s.setdefault("pattern", 25)
        next_p = max(9, min(41, int(s["pattern"]) + 2))
        # schedule only if no move in last 10 frames
        if (now_f - int(s.get("last_any_change_frame", -10**9))) >= 10:
            s["scheduled"].append({"type": "pattern", "value": next_p, "apply_at": now_f + 1})
            # Sperre weitere Schedules bis Anwendung erfolgt
            s["erosion_counter"] = 0


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
                s["pattern"] = int(ev.get("value", s.get("pattern", 25)))
                s["last_pattern_change_frame"] = now_f
                s["last_any_change_frame"] = now_f
        else:
            keep.append(ev)
    s["scheduled"] = keep


# ———————————— Convenience ————————————

def get_online_state(roi_id) -> Dict[str, Any]:
    """Gibt eine Kopie des internen Zustands für Debug/UI zurück."""
    s = _roi_state(int(roi_id)).copy()
    # keine Markerlisten leaken (hier Platzhalter leer)
    s.pop("markers", None)
    return s