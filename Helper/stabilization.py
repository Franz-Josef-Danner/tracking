# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/stabilization.py – Peer-Stabilisierung & Reseeding

- Peer-Snap: Sprungbegrenzung relativ zur Clustertrajektorie (Platzhalter)
- Koordiniertes Re-Template (Stub)
- Reseeding in Coverage-Löchern (Tiles-Priorisierung)
- Periodische Cleanup-Passes (ruft vorhandene Cleanups)
"""
from __future__ import annotations

from typing import Dict, Any

from .strm import ROI

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

from . import clean_error_tracks as CET
from . import clean_short_tracks as CST
from . import clean_short_segments as CSS
from . import refine_high_error as RHE

__all__ = ("peer_snap_and_refresh", "reseed_coverage_holes", "periodic_cleanup")


def peer_snap_and_refresh(context, roi: ROI) -> Dict[str, Any]:
    # Platzhalter – kein Eingriff
    return {"status": "READY"}


def reseed_coverage_holes(context, roi: ROI) -> Dict[str, Any]:
    # Platzhalter – heuristisch: keine Aktion
    return {"status": "READY"}


def periodic_cleanup(context, roi: ROI | None = None) -> Dict[str, Any]:
    # Führt leichte Cleanups aus; ignoriert Fehler
    stats = {}
    try:
        CET.run_clean_error_tracks(context)
        stats["clean_error_tracks"] = True
    except Exception:
        stats["clean_error_tracks"] = False
    try:
        CSS.run_clean_short_segments(context)
        stats["clean_short_segments"] = True
    except Exception:
        stats["clean_short_segments"] = False
    try:
        CST.run_clean_short_tracks(context)
        stats["clean_short_tracks"] = True
    except Exception:
        stats["clean_short_tracks"] = False

    return {"status": "READY", "stats": stats}
