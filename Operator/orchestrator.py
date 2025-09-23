from __future__ import annotations
from typing import Any, Dict

from ..Helper.init_params import init_pattern_search
from ..Helper.detect_autotune import propose_detect_profile, adjust_detect_profile
from ..Helper.staged_seeding import staged_detect_with_dedup


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


def run_autotrack(context, clip) -> dict:
    """
    Dünne, lauffähige Orchestrierung des Minimalpfads:
      - Startwerte (pattern/alpha/search)
      - Detect-Profil (Vorschlag + leichte Justage)
      - Gestuftes Seeding mit Dedup/Micro-Validation
    Return: einfache Telemetrie/KPIs.
    """
    scn = getattr(context, "scene", None)

    _try_marker_baseline(context)

    width, height = _clip_size(clip)

    # Marker-Ziel ableiten (robust, ohne UI-Abhängigkeit)
    marker_frame = int(getattr(scn, "marker_frame", 25)) if scn else 25
    factor = int(getattr(scn, "marker_factor", 4)) if scn else 4
    total_target = int(max(1, marker_frame * factor))

    # STRM/ROI (Platzhalter): eine ROI mit neutralen Scores
    texture = 0.5
    motion = 0.5

    # Startparameter
    pattern, alpha, search = init_pattern_search(width, height, motion_score=motion)

    # Detect-Profil
    profile = propose_detect_profile(roi_id=0, texture=texture, motion=motion)
    # einfache KPI-Attrappe für mögliche Anpassungen
    fake_kpis: Dict[str, Any] = {"coverage": 0.0, "target_coverage": 0.8, "texture": texture}
    profile = adjust_detect_profile(fake_kpis, profile)

    # Szene-Paket für Seeding
    scene_pkg: Dict[str, Any] = {
        "detect_profile": profile,
        "channel": "Y",
        "existing_markers": [],
        "context": context,
        "clip": clip,
        "search": search,
    }

    # Gestufte Setzung ausführen
    summary = staged_detect_with_dedup(
        roi_id=0,
        pattern=pattern,
        alpha=alpha,
        total_target=total_target,
        scene=scene_pkg,
    )

    # Ergebnis zusammenstellen (Minimal-KPIs)
    result = {
        "roi_count": 1,
        "clip_size": (width, height),
        "pattern": pattern,
        "alpha": alpha,
        "search": search,
        "detect_profile": profile,
        "seeding": summary,
    }
    return result
