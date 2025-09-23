# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/online_adapt.py – One-Frame Tracking Loop (online adaptiv)

- Cheap-Move (α-Only) pro Frame
- Gated-Move (Pattern) auf Checkpoints mit Hysterese/Triggerzählern
- Param-Änderungen stets "apply-next-frame" (keine Mid-Frame-Änderung)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any

from .strm import ROI
from .governance import LIMITS

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

__all__ = ("track_one_frame", "schedule_param_changes")


@dataclass
class OnlineState:
    last_alpha: int = 3
    last_pattern: int = 15
    cooldown: int = 0
    trig_stable: int = 0
    trig_unstable: int = 0


def _get_ts(context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip and bpy is not None:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            clip = None
    return clip.tracking.settings if clip else None


def track_one_frame(context, roi: ROI, telem: Dict[str, Any], state: OnlineState | None = None) -> Dict[str, Any]:
    """Trackt 1 Frame vorwärts. Passt alpha (search/pattern) adaptiv an und plant Änderungen für t+1.
    telem erwartet Keys wie corr (Korrelation) und fail_flag.
    """
    state = state or OnlineState(last_alpha=roi.alpha, last_pattern=roi.pattern)

    # Cheap move: nur alpha
    corr = float(telem.get("corr", 0.95))
    fail = bool(telem.get("fail", False))

    a = int(state.last_alpha)
    if fail or corr < 0.6:
        a = max(LIMITS.alpha_min, a - 1)
        state.trig_unstable += 1
        state.trig_stable = 0
    else:
        # stabil und ggf. teuer → alpha runter
        if corr > 0.9:
            a = max(LIMITS.alpha_min, a - 1)
        else:
            # Abriss ohne Fehlmatch (Proxy): alpha + 1, aber ≤4
            a = min(LIMITS.alpha_max, a + 1)
        state.trig_stable += 1
        state.trig_unstable = 0

    roi.alpha = int(a)

    # Geplanten Search anwenden (next frame)
    search_next = int(max(2, 2 * roi.pattern))
    search_next = int(min(4 * roi.pattern, search_next))

    schedule_param_changes(context, roi, changes={"alpha": roi.alpha, "search": search_next})

    # Tatsächlich tracken (UI-invoked, nicht blockierend)
    try:
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=False)
    except Exception:
        pass

    return {
        "status": "READY",
        "alpha_next": roi.alpha,
        "search_next": search_next,
        "state": state,
    }


def schedule_param_changes(context, roi: ROI, changes: Dict[str, Any]) -> None:
    ts = _get_ts(context)
    if not ts:
        return
    a = int(changes.get("alpha", roi.alpha))
    p = int(roi.pattern)
    search = int(changes.get("search", 2 * p))
    # Grenzen
    a = LIMITS.clamp_alpha(a)
    if hasattr(ts, "default_pattern_size"):
        try:
            p = LIMITS.clamp_pattern(p)
            ts.default_pattern_size = int(p)
        except Exception:
            pass
    if hasattr(ts, "default_search_size"):
        try:
            ts.default_search_size = int(search)
        except Exception:
            pass

    # Publish to scene (apply-next-frame Semantik)
    if bpy is not None:
        scn = bpy.context.scene
        scn["kc_next_alpha"] = int(a)
        scn["kc_next_pattern"] = int(p)
        scn["kc_next_search"] = int(search)
