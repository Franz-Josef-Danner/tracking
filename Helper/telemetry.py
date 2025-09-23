# KPIs/Logs, Score-Aggregation, Zeitbudget
import os
import json
import time
from typing import Dict, Any

_DEF_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), ".telemetry"
)
_DEF_FILE = os.path.join(_DEF_DIR, "log.jsonl")


def log_step(scope: str, payload: dict) -> None:
    os.makedirs(_DEF_DIR, exist_ok=True)
    entry = {"ts": int(time.time() * 1000), "scope": str(scope), "payload": payload or {}}
    try:
        with open(_DEF_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def aggregate_kpis() -> dict:
    if not os.path.exists(_DEF_FILE):
        return {}
    total = 0
    by_scope = {}
    try:
        with open(_DEF_FILE, "r", encoding="utf-8") as f:
            for line in f:
                total += 1
                try:
                    d = json.loads(line)
                    s = d.get("scope", "?")
                    by_scope[s] = by_scope.get(s, 0) + 1
                except Exception:
                    continue
    except Exception:
        return {}
    return {"events": total, "by_scope": by_scope}


def finalize_metrics() -> dict:
    return aggregate_kpis()


def time_budget_hit(roi_id) -> bool:
    return False


# ———————————— Governance / KPI Scoring ————————————

def _sf(v, default: float) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def compute_target_score(kpis: Dict[str, Any]) -> float:
    """Berechne einen Zielscore (niedriger ist besser) gemäß Gewichten.
    Erwartete Felder (optional):
      - survival (0..1), bevorzugt Survival@30f
      - corr_med (0..1)
      - time_norm (0..1), normalisierte Zeitkosten
    Fallbacks auf konservative Defaults.
    """
    survival_30 = _sf(kpis.get("survival_30", 0.6), 0.6)
    survival = _sf(kpis.get("survival", survival_30), survival_30)
    corr_med = _sf(kpis.get("corr_med", 0.6), 0.6)
    time_norm = _sf(kpis.get("time_norm", 0.5), 0.5)
    score = 0.5 * (1.0 - survival) + 0.3 * (1.0 - corr_med) + 0.2 * time_norm
    return float(score)