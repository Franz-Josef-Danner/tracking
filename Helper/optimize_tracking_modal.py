# Blender-Add-on – funktionaler Optimierungs‑Flow (keine Operatoren)
#
# Ziel
# ----
# Die funktionale Portierung der alten, bewährten Optimierung in eine reine
# Funktions‑API. Es gibt **keine** Operatoren in diesem Modul. Stattdessen werden
# Timer‑Callbacks (``bpy.app.timers``) benutzt, um nicht-blockierend zu arbeiten.
#
# Vorgaben des Nutzers
# --------------------
# • Regel 1: kein Operator, nur Funktionen zum Aufrufen.
# • Die Aufrufe für Detect & Track bleiben identisch zur neuen Version
#   (d. h. wir verwenden dieselben Helper‑Funktionen wie dort).
#
# Pseudo‑Code (vereinfacht übertragen)
# ------------------------------------
#
#     default setzen: pt = Pattern Size, sus = Search Size
#     flag1 setzen (Pattern/Search übernehmen)
#     Marker setzen
#     track → für jeden Track: f_i = Frames pro Track, e_i = Error → eg_i = f_i / e_i
#     ega = Σ eg_i
#     if ev < 0:
#         ev = ega; pt *= 1.1; sus = pt*2; flag1
#     else:
#         if ega > ev:
#             ev = ega; dg = 4; ptv = pt; pt *= 1.1; sus = pt*2; flag1
#         else:
#             dg -= 1
#             if dg >= 0:
#                 pt *= 1.1; sus = pt*2; flag1
#             else:
#                 // Motion‑Model‑Schleife (0..4)
#                 Pattern size = ptv; Search = ptv*2; flag2 setzen
#                 marker setzen; tracken; … → beste Motion wählen
#                 // Channel‑Schleife (vv 0..3), R/G/B‑Kombis laut Vorgabe
#
# API‑Überblick
# -------------
# • ``start_optimization(context)`` – öffentlicher Einstieg, startet Ablauf.
# • ``cancel_optimization()`` – bricht ggf. laufende Optimierung ab.
# • Ablauf läuft über ``bpy.app.timers`` und setzt intern Status/Token.
#
# Abhängigkeiten (Helper)
# -----------------------
# Wir verwenden dieselben Helper-Funktionen wie in der neuen Version:
# • ``detect.run_detect_once(context, start_frame: int, handoff_to_pipeline=False)``
# • ``tracking_helper.track_to_scene_end_fn(context, coord_token: str, start_frame: int, ...)``
#
# Beide werden dynamisch importiert; fehlen sie, wird sauber abgebrochen.
#
# Hinweis: Dieses Modul ist bewusst selbsterklärend und ausführlich kommentiert,
# um die Logik später leicht anpassen zu können.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

import bpy

# -----------------------------------------------------------------------------
# Dynamische Helper‑Imports (gleichen Signaturen wie in optimize_tracking_modal_neu)
# -----------------------------------------------------------------------------
try:  # Detect-Einzelpass
    from .detect import run_detect_once  # type: ignore
except Exception:  # pragma: no cover
    run_detect_once = None  # type: ignore

try:  # Async‑Tracking bis Szenenende, setzt ein Done‑Token im WindowManager
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

try:  # Fehler/Qualitätsmetrik (aus altem System)
    from .error_value import error_value  # type: ignore
except Exception:  # pragma: no cover
    error_value = None  # type: ignore

# perform_marker_detection wird indirekt in detect.run_detect_once verwendet.

# -----------------------------------------------------------------------------
# Konfiguration & Mapping
# -----------------------------------------------------------------------------
MOTION_MODELS: List[str] = [
