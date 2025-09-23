# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/governance.py

Governance, Budgets, Kennzahlen (KPIs) und Zielscore.

Ziele:
- Deterministische Seeds (pro ROI/Trial/Stage) für reproduzierbare Micro-Trials
- Zeit-Slicing / ROI- und Stage-Budgets
- KPI-Erfassung solve-frei: Survival@10/30f, Corr-Median, Residual-RMS, Coverage, Redundanz-Index, Zeit/Frame
- Zielscore (Qualität vs. Speed) zur Presetwahl und Vergleichbarkeit
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import time
import math
import random

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover - im Editor evtl. nicht vorhanden
    bpy = None  # type: ignore

# ------------------------------------------------------------
# Seeds & Namespaces
# ------------------------------------------------------------

def make_seed(namespace: str, roi_id: str, stage: int, frame: int) -> int:
    """Deterministischer Seed auf Basis von Namespace/ROI/Stage/Frame."""
    key = f"{namespace}|{roi_id}|{stage}|{frame}"
    # Simple 64-bit hash
    h = 1469598103934665603
    for ch in key.encode("utf-8"):
        h ^= ch
        h *= 1099511628211
        h &= (1 << 64) - 1
    return int(h & 0x7FFFFFFF)


def seed_rng(namespace: str, roi_id: str, stage: int, frame: int) -> None:
    random.seed(make_seed(namespace, roi_id, stage, frame))

# ------------------------------------------------------------
# Budgets / Timeslicing
# ------------------------------------------------------------

@dataclass
class TimeBudget:
    # Sekunden pro ROI und optional pro Stage
    seconds_total: float = 0.25
    seconds_stage: float = 0.05
    # max. Parameteränderungen: 1 Move / 10 Frames / Marker
    max_param_moves_per_10f: int = 1

    # intern
    _t_start: float = field(default=0.0, init=False)
    _spent: float = field(default=0.0, init=False)

    def start(self) -> None:
        self._t_start = time.perf_counter()

    def stop_and_accumulate(self) -> None:
        if self._t_start > 0.0:
            self._spent += max(0.0, time.perf_counter() - self._t_start)
            self._t_start = 0.0

    def remaining_total(self) -> float:
        return max(0.0, self.seconds_total - self._spent)

    def allow_stage(self) -> bool:
        return self.remaining_total() >= max(0.0, float(self.seconds_stage))

# ------------------------------------------------------------
# KPIs / Telemetrie
# ------------------------------------------------------------

@dataclass
class KPI:
    survival10: float = 0.0
    survival30: float = 0.0
    corr_median: float = 0.0
    residual_rms: float = 0.0
    coverage_tiles: float = 0.0
    redundancy_index: float = 0.0  # 1/d_nn
    time_per_frame_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "survival10": float(self.survival10),
            "survival30": float(self.survival30),
            "corr_median": float(self.corr_median),
            "residual_rms": float(self.residual_rms),
            "coverage_tiles": float(self.coverage_tiles),
            "redundancy_index": float(self.redundancy_index),
            "time_per_frame_ms": float(self.time_per_frame_ms),
        }


def composite_score(k: KPI, *, w_quality: float = 0.7, w_speed: float = 0.3) -> float:
    """Gewichteter Zielscore in px-equiv (niedriger ist besser):
    S = w_quality * Q + w_speed * T
    mit Q ~ Fehlermaß aus (1-survival, 1-corr, residual) und T ~ Zeitnorm 0..1.
    """
    # Heuristiken, normiert 0..1
    q_surv = 0.5 * (1.0 - max(0.0, min(1.0, k.survival10))) + 0.5 * (1.0 - max(0.0, min(1.0, k.survival30)))
    q_corr = 1.0 - max(0.0, min(1.0, k.corr_median))
    q_resi = max(0.0, min(1.0, k.residual_rms / 3.0))  # 3px als grobe Norm
    q_cov = 1.0 - max(0.0, min(1.0, k.coverage_tiles))
    q_red = 1.0 - max(0.0, min(1.0, k.redundancy_index))
    Q = 0.35 * q_surv + 0.35 * q_corr + 0.20 * q_resi + 0.05 * q_cov + 0.05 * q_red

    # Zeit: 16ms ~ 1x, >80ms -> 1.0
    T = max(0.0, min(1.0, k.time_per_frame_ms / 80.0))
    return float(w_quality * Q + w_speed * T)

# ------------------------------------------------------------
# Scene-Integration
# ------------------------------------------------------------

def publish_telem_on_scene(k: KPI, *, prefix: str = "kc_kpi_") -> None:
    if bpy is None:
        return
    scn = bpy.context.scene
    scn[f"{prefix}survival10"] = float(k.survival10)
    scn[f"{prefix}survival30"] = float(k.survival30)
    scn[f"{prefix}corr_median"] = float(k.corr_median)
    scn[f"{prefix}residual_rms"] = float(k.residual_rms)
    scn[f"{prefix}coverage_tiles"] = float(k.coverage_tiles)
    scn[f"{prefix}redundancy_index"] = float(k.redundancy_index)
    scn[f"{prefix}time_per_frame_ms"] = float(k.time_per_frame_ms)


def publish_score_on_scene(score: float, *, key: str = "kc_goal_score") -> None:
    if bpy is None:
        return
    bpy.context.scene[key] = float(score)

# ------------------------------------------------------------
# Guards / Grenzen
# ------------------------------------------------------------

@dataclass
class SafetyLimits:
    pattern_min: int = 9
    pattern_max: int = 41
    alpha_min: int = 2
    alpha_max: int = 4
    search_rel_max: float = 0.12  # Anteil von minDim

    def clamp_pattern(self, p: int) -> int:
        return max(self.pattern_min, min(self.pattern_max, int(p)))

    def clamp_alpha(self, a: int) -> int:
        return max(self.alpha_min, min(self.alpha_max, int(a)))

    def clamp_search(self, search: int, width: int, height: int) -> int:
        limit = int(self.search_rel_max * min(width, height))
        return min(int(search), int(limit))

LIMITS = SafetyLimits()
