# Helper/init_detect_state.py
import bpy
from typing import Dict, Any, Set
from .util_clip import get_active_clip
from .snapshot import snapshot_active_markers
from .detect_config import get_detect_params

def init_detect_state(context: bpy.types.Context) -> Dict[str, Any]:
    """
    Initialisiert alle Erkennungsparameter (hz, vc, margin, threshold, etc.)
    und erfasst Baseline-Marker & Tracks.
    Gibt ein Dict zurück mit allen Startwerten für Detect/Tracking.
    """
    scene = context.scene
    clip = get_active_clip(context)
    if not clip:
        raise RuntimeError("Kein aktiver MovieClip verfügbar.")

    # 1) Detect-Parameter
    params = get_detect_params(context)
    hz, vc = params["hz"], params["vc"]
    margin = params["margin"]
    pattern_size = params["pattern_size"]
    search_size = params["search_size"]
    threshold = params["threshold"]
    min_distance = params["min_distance"]

    # 2) min_distance ggf. aus Szeneninterpolation laden
    frame_num = scene.frame_current
    if "min_distance_values" in scene:
        md_dict = scene["min_distance_values"]
        if str(frame_num) in md_dict:
            min_distance = float(md_dict[str(frame_num)])
        elif "known_frames" in md_dict and len(md_dict["known_frames"]) >= 2:
            known = sorted(md_dict["known_frames"])
            prev = [f for f in known if f < frame_num]
            nxt = [f for f in known if f > frame_num]
            if prev and nxt:
                f1, f2 = max(prev), min(nxt)
                v1, v2 = float(md_dict[str(f1)]), float(md_dict[str(f2)])
                t = (frame_num - f1) / (f2 - f1)
                min_distance = v1 + (v2 - v1) * t

    # 3) Marker-Baseline erfassen
    snapshot = snapshot_active_markers(context)
    baseline_start_tracknames: Set[str] = {t.name for t in clip.tracking.tracks}

    return {
        "hz": hz,
        "vc": vc,
        "margin": margin,
        "pattern_size": pattern_size,
        "search_size": search_size,
        "threshold": threshold,
        "min_distance": min_distance,
        "snapshot": snapshot,
        "baseline_tracks": baseline_start_tracknames,
    }
