# Dünne Koordination der Helper (keine Heavy-Logik)
from __future__ import annotations
import os
import json
from typing import Any, Dict


_DEF_PATH = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), ".presets", "presets.json")


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    os.makedirs(d, exist_ok=True)


def _make_key(clip_id: str, roi_signature: dict) -> str:
    sig = {
        "res": roi_signature.get("resolution"),
        "tex": roi_signature.get("texture_bin"),
        "mot": roi_signature.get("motion_bin"),
        "quad": roi_signature.get("quadrant"),
    }
    return f"{clip_id}:{json.dumps(sig, sort_keys=True)}"


def _load_all(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(path: str, data: Dict[str, Any]) -> None:
    _ensure_dir(path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_preset(clip_id: str, roi_signature: dict) -> dict | None:
    """Return Startwerte für ähnliche Fälle (Resolution/Texture/Motion/Quadrant)."""
    store = _load_all(_DEF_PATH)
    key = _make_key(clip_id, roi_signature or {})
    return store.get(key)


def save_preset(clip_id: str, roi_signature: dict, params: dict, score: float) -> None:
    """Persistiere Best-Params; apply Aging & ε-greedy Exploration (TODO)."""
    store = _load_all(_DEF_PATH)
    key = _make_key(clip_id, roi_signature or {})
    entry = store.get(key, {})
    # speichere die besseren Werte (niedrigere Score ist besser gemäß Vorgabe)
    best = entry.get("score")
    if best is None or float(score) < float(best):
        store[key] = {"params": params or {}, "score": float(score)}
        _save_all(_DEF_PATH, store)


def write_presets() -> bool:
    """Persistenz ist immediate; diese Funktion dient als Schnittstellen-Hook.
    Gibt True zurück, wenn eine Preset-Datei existiert.
    """
    try:
        return bool(_load_all(_DEF_PATH))
    except Exception:
        return False