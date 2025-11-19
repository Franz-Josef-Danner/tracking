# Helper/reference_key.py
import bpy
from typing import List, Optional
import ast

# ------------------------------------------------------------
# Utility zum Laden einer Namensliste aus Szene
# ------------------------------------------------------------
def _load_name_list(scene: bpy.types.Scene, key: str) -> List[str]:
    """Extrahiert eine Tracknamensliste aus *_names Properties."""
    raw = scene.get(key)
    if raw is None:
        return []

    # Falls literal abgespeichert
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
            if isinstance(parsed, dict):
                return [str(v).strip() for v in parsed.values() if str(v).strip()]
            # Fallback: CSV
            return [s.strip() for s in raw.split(",") if s.strip()]
        except Exception:
            return [s.strip() for s in raw.split(",") if s.strip()]

    # Falls echte Liste
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]

    # Falls Dict (UUID-Map)
    if isinstance(raw, dict):
        return [str(v).strip() for v in raw.values() if str(v).strip()]

    return []


# ------------------------------------------------------------
# Trackpriorisierung (jetzt korrekt: *_names-Liste)
# ------------------------------------------------------------
def get_reference_tracks(scene: bpy.types.Scene) -> List[str]:
    """Zentrale Referenzlogik für Forward & Backward.
    Priorität: best_tracks > good_tracks > calibrate_tracks > none.
    Liefert nur valide Tracknamen zurück."""

    # 1) Best hat höchste Priorität
    if scene.get("best_tracks_names"):
        best = _load_name_list(scene, "best_tracks_names")
        if best:
            return best

    # 2) Good
    if scene.get("good_tracks_names"):
        good = _load_name_list(scene, "good_tracks_names")
        if good:
            return good

    # 3) Fallback: Calibrate Tracks (selbst wenn begrenzt)
    if scene.get("calibrate_tracks_names"):
        cal = _load_name_list(scene, "calibrate_tracks_names")
        if cal:
            return cal

    # 4) Nichts vorhanden
    return []


# ------------------------------------------------------------
# Validierung gegen real existierende Tracks im Clip
# ------------------------------------------------------------
def filter_existing_tracks(context, names: List[str]) -> List[str]:
    """Validiert Tracknamen gegen den aktiven Clip."""
    clip = getattr(context.space_data, "clip", None)
    if not clip or not clip.tracking:
        return []
    tracking = clip.tracking
    return [n for n in names if n in tracking.tracks]
