# Frameweise α-Adjust + gated Pattern-Wechsel (apply-next)
from __future__ import annotations
from typing import Dict, Any
import time

# einfacher In-Memory-Zustand je ROI/Marker
_STATE: Dict[int, Dict[str, Any]] = {}


def _roi_state(roi_id: int) -> Dict[str, Any]:
    s = _STATE.setdefault(int(roi_id), {"markers": {}, "scheduled": [], "last_change": 0})
    return s


def track_one_frame(roi_id) -> dict:
    """1-Step-Tracking für alle Marker im ROI; return Telemetrie-Aggregate.

    Placeholder: liefert stabilen Zustand ohne echte Bildverarbeitung.
    """
    s = _roi_state(int(roi_id))
    n = len(s.get("markers", {}))
    tel = {"markers": n, "mismatch_rate": 0.0, "corr_med": 0.8, "runtime_ms": 1.0}
    return tel


def schedule_param_changes(roi_id, telemetry: dict) -> None:
    """Pro Marker: α-Adjust (cheap) live; Pattern-Change gated (apply-next).

    Minimal: wenn corr_med < 0.65 → α+1, wenn >0.8 und runtime hoch → α-1.
    Pattern-Wechsel nur alle ≥15 Frames (Cooldown) und bei stabiler Lage.
    """
    s = _roi_state(int(roi_id))
    corr = float(telemetry.get("corr_med", 0.8))
    runtime = float(telemetry.get("runtime_ms", 1.0))
    # cheap alpha adjust
    if corr < 0.65:
        s.setdefault("alpha", 3)
        s["alpha"] = min(4, int(s["alpha"]) + 1)
    elif corr > 0.8 and runtime > 2.0:
        s.setdefault("alpha", 3)
        s["alpha"] = max(2, int(s["alpha"]) - 1)

    # gated pattern adjust (apply-next) – Platzhalter-Trigger
    now = int(time.time() * 1000)
    if now - int(s.get("last_change", 0)) > 15000 and 0.7 <= corr <= 0.8:
        s.setdefault("pattern", 25)
        next_p = max(9, min(41, int(s["pattern"]) + 2))
        s["scheduled"].append({"type": "pattern", "value": next_p})
        s["last_change"] = now


def apply_scheduled_next_frame(roi_id) -> None:
    """Pattern-Wechsel mit Re-Template (Medianfenster), Lock & Cooldown.

    Minimal: setzt geplante Änderungen sofort um.
    """
    s = _roi_state(int(roi_id))
    sch = list(s.get("scheduled", []))
    s["scheduled"] = []
    for ev in sch:
        if ev.get("type") == "pattern":
            s["pattern"] = int(ev.get("value", s.get("pattern", 25)))