# Helper/reference_key.py
import bpy
from typing import List, Optional

def get_reference_tracks(scene: bpy.types.Scene) -> List[str]:
    """Zentrale Referenzlogik für Forward & Backward.
    Priorität: best_tracks > good_tracks > calibrate_tracks > none.
    Liefert nur valide Tracknamen zurück."""
    
    # 1) Best
    best_raw = scene.get("best_tracks", "")
    if isinstance(best_raw, str) and best_raw.strip():
        best = [t.strip() for t in best_raw.split(",") if t.strip()]
        if best:
            return best

    # 2) Good
    good_raw = scene.get("good_tracks", "")
    if isinstance(good_raw, str) and good_raw.strip():
        good = [t.strip() for t in good_raw.split(",") if t.strip()]
        if good:
            return good

    # 3) Calibrate fallback
    cal_raw = scene.get("calibrate_tracks", "")
    if isinstance(cal_raw, str) and cal_raw.strip():
        cal = [t.strip() for t in cal_raw.split(",") if t.strip()]
        if cal:
            return cal

    # 4) Nichts gefunden
    return []


def filter_existing_tracks(context, names: List[str]) -> List[str]:
    """Validiert Tracknamen gegen den aktiven Clip."""
    clip = getattr(context.space_data, "clip", None)
    if not clip or not clip.tracking:
        return []

    tracking = clip.tracking
    return [n for n in names if n in tracking.tracks]
