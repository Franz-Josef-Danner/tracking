# Helper/marker_helper_main.py
import bpy
from typing import Tuple, Dict, Any

__all__ = ("marker_helper_main",)

def marker_helper_main(context) -> Tuple[bool, int, Dict[str, Any]]:

    scn = context.scene

    # Source of Truth aus der Szene
    marker_basis   = int(getattr(scn, "marker_frame", 25))     # gewünschte Marker/Frame (UI)
    frames_track   = int(getattr(scn, "frames_track", 25))     # Ziel-Tracklänge (UI)
    resolve_error  = float(getattr(scn, "resolve_error", 2.0)) # Solve-Grenzwert (UI)

    # Ableitungen (klassische Heuristik)
    factor         = int(getattr(scn, "marker_factor", 4))     # optionaler UI-Faktor; Default 4
    marker_adapt   = int(marker_basis * factor)
    marker_min     = int(max(1, round(marker_adapt * 0.9)))
    marker_max     = int(max(2, round(marker_adapt * 1.1)))

    # Persistenz
    scn["marker_basis"]  = int(marker_basis)   # <- FIND_LOW nutzt diesen Basiswert
    scn["marker_adapt"]  = int(marker_adapt)
    scn["marker_min"]    = int(marker_min)
    scn["marker_max"]    = int(marker_max)
    scn["frames_track"]  = int(frames_track)
    scn["resolve_error"] = float(resolve_error)

    # Telemetrie

    return True, int(marker_adapt), {"FINISHED"}
