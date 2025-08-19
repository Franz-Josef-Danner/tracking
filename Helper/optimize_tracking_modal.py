"""Blender-Add-on – funktionaler Optimierungs‑Flow (keine Operatoren)

NEU in dieser Variante
----------------------
• Vor der Motion/Channel‑Optimierung läuft nun ein **Pattern‑Size‑Sweep**,
  der erst beendet wird, wenn die Qualitätsmetrik (EGA) **signifikant**
  unter den bisher besten Wert fällt (relativer Abstieg > drop_threshold),
  und **mindestens min_sweep_steps** Samples gesammelt wurden.
• Beste (pt, sus) aus dem Sweep werden als ptv festgehalten und anschließend
  in die Motion‑/Channel‑Schleifen übernommen.

Parameter
---------
• sweep_step_factor: Multiplikator für Pattern‑Size‑Erhöhung pro Schritt (Default 1.1)
• drop_threshold:     relativer Abstieg gegenüber best_ega, z. B. 0.12 = 12%
• min_sweep_steps:    Mindestanzahl von Messpunkten, bevor abgebrochen werden darf
• soft_patience:      Anzahl tolerierter **nicht**‑signifikanter Nicht‑Verbesserungen,
                       bevor wir vorsorglich beenden (Failsafe)

Hinweis
-------
Die restliche Struktur (Detect/Track‑Helper, Motion‑ & Channel‑Loops) bleibt
unverändert. Der frühere DG‑Zähler entfällt im Sweep und wird durch die klare
Abbruchbedingung „signifikanter Abstieg“ ersetzt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

import bpy

# -----------------------------------------------------------------------------
# Dynamische Helper‑Imports (wie in der neuen Variante)
# -----------------------------------------------------------------------------
try:
    from .detect import run_detect_once  # type: ignore
except Exception:  # pragma: no cover
    run_detect_once = None  # type: ignore

try:
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

try:
    from .error_value import error_value  # type: ignore
except Exception:  # pragma: no cover
    error_value = None  # type: ignore

# -----------------------------------------------------------------------------
# Konfiguration & Mapping
# -----------------------------------------------------------------------------
MOTION_MODELS: List[str] = [
    "Perspective",
    "Affine",
    "LocRotScale",
    "LocScale",
    "LocRot",
]

CHANNEL_PRESETS = {
    0: (True, False, False),
    1: (True, True, False),
    2: (False, True, False),
    3: (False, True, True),
}

# -----------------------------------------------------------------------------
# Flag‑Setter
# -----------------------------------------------------------------------------

def _set_flag1(clip: bpy.types.MovieClip, pattern: int, search: int) -> None:
    s = clip.tracking.settings
    s.default_pattern_size = int(pattern)
    s.default_search_size = int(search)
    s.default_margin = s.default_search_size


def _set_flag2_motion_model(clip: bpy.types.MovieClip, model_index: int) -> None:
    if 0 <= model_index < len(MOTION_MODELS):
        clip.tracking.settings.default_motion_model = MOTION_MODELS[model_index]
