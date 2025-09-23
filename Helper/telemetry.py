# KPIs/Logs, Score-Aggregation, Zeitbudget
import os
import json
import time

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


def time_budget_hit(roi_id) -> bool:
    return False