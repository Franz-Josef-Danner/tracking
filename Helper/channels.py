# Kanal-Analyse & -Selektion (Pre-Pass + Micro-Trials)
from __future__ import annotations
from typing import Dict, List

# einfacher Zustand für Hysterese
_LAST_CH: Dict[int, str] = {}
_NEG_WINDOW: Dict[int, int] = {}


def analyze_channels(roi_id, sample_frames: list[int]) -> dict:
    """Return per-channel Pre-Scores (texture, stability, penalty).

    Minimal: fixe Heuristik, die Y/G bevorzugt; andere Kanäle neutralisieren.
    """
    channels = ["Y", "G", "R", "B"]
    out: Dict[str, Dict] = {}
    for ch in channels:
        if ch in ("Y", "G"):
            out[ch] = {"texture": 0.6, "stability": 0.6, "penalty": 0.0}
        else:
            out[ch] = {"texture": 0.4, "stability": 0.5, "penalty": 0.05}
    return out


def trial_track_channel(roi_id, channel: str, window: int = 30) -> dict:
    """Run Micro-Trial; return {survival, corr_med, time_norm, score}.

    Minimal: synthetischer Score mit leichter Präferenz für Y/G.
    """
    base = 0.6 if channel in ("Y", "G") else 0.5
    survival = base
    corr_med = base
    time_norm = 0.5
    score = 0.5 * (1.0 - survival) + 0.3 * (1.0 - corr_med) + 0.2 * time_norm
    return {"survival": survival, "corr_med": corr_med, "time_norm": time_norm, "score": score}


def select_channel(roi_id, pattern: int, alpha: int) -> str:
    """Shortlist + Micro-Trial → return best channel ('Y','G','R','B','Y_EQ').

    Minimal: shortlist {Y,G}, Hysterese: Wechsel erst nach 2 negativen Fenstern.
    """
    shortlist = ["Y", "G"]
    best_ch, best_score = None, 1e9
    for ch in shortlist:
        t = trial_track_channel(roi_id, ch, window=30)
        if t["score"] < best_score:
            best_score, best_ch = t["score"], ch

    prev = _LAST_CH.get(int(roi_id))
    if prev and prev != best_ch:
        cnt = _NEG_WINDOW.get(int(roi_id), 0) + 1
        _NEG_WINDOW[int(roi_id)] = cnt
        if cnt < 2:
            return prev
        else:
            _NEG_WINDOW[int(roi_id)] = 0
    _LAST_CH[int(roi_id)] = best_ch or "Y"
    return best_ch or "Y"