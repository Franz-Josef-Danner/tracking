# Helper/pattern_threshold_recovery.py
import bpy

# ============================================================
# Public API
# ============================================================
def run_pattern_threshold_recovery(context) -> str:
    """
    Führt einen Pattern-Size/Threshold-Recovery-Check aus.

    Rückgabe:
        "SKIP"       → Threshold wurde gebostet, Operator soll Hard-Exit machen.
        "CONTINUE"   → Normale Weiterverarbeitung ohne Threshold-Anpassung.
        "NO_PATTERN" → Keine Pattern Size lesbar, nichts getan.
    """
    scene = context.scene

    # ------------------------------------------------------------
    # 1) Pattern sicher aus Tracking Settings holen
    # ------------------------------------------------------------
    current_pz = _read_default_pattern_size(context)
    if current_pz is None:
        return "NO_PATTERN"

    # ------------------------------------------------------------
    # 2) Vorherigen Referenzwert holen
    # ------------------------------------------------------------
    try:
        last_pz = int(scene.get("kaiserlich_last_pattern_size_recovery", 0))
    except Exception:
        last_pz = 0

    #-------------------------------------------------------------
    # 3) Case: Pattern kleiner als zuletzt → Hard Threshold Boost
    #-------------------------------------------------------------
    if current_pz < last_pz:
        _boost_threshold(scene)
        scene["kaiserlich_last_pattern_size_recovery"] = int(current_pz)
        return "SKIP"

    #-------------------------------------------------------------
    # 4) Case: Pattern gleich oder größer → Nur Referenz speichern
    #-------------------------------------------------------------
    scene["kaiserlich_last_pattern_size_recovery"] = int(current_pz)
    return "CONTINUE"


# ============================================================
# Internal Tools
# ============================================================

def _read_default_pattern_size(context):
    """Robust den default_pattern_size aus aktuellem Clip/Space/Scene lesen."""
    tracking_settings = None
    scr = getattr(context, "screen", None)

    # Try UI Areas
    try:
        if scr and hasattr(scr, "areas"):
            for _area in scr.areas:
                if _area.type == 'CLIP_EDITOR':
                    for _space in _area.spaces:
                        if _space.type == 'CLIP_EDITOR' and getattr(_space, "clip", None):
                            settings = getattr(_space.clip.tracking, "settings", None)
                            if settings:
                                tracking_settings = settings
                                break
                if tracking_settings:
                    break
    except Exception:
        pass

    # Try space_data
    if not tracking_settings:
        try:
            sp = getattr(context, "space_data", None)
            if sp and getattr(sp, "clip", None):
                tracking_settings = getattr(sp.clip.tracking, "settings", None)
        except Exception:
            pass

    if not tracking_settings:
        return None

    try:
        raw_val = getattr(tracking_settings, "default_pattern_size", None)
        if isinstance(raw_val, int) and 5 <= raw_val <= 1000:
            return raw_val
    except Exception:
        pass
    return None


def _boost_threshold(scene):
    """Erhöht tr-Wert um Faktor 10 und persistiert ihn."""
    params = scene.get("bootstrap_params", {})
    if not isinstance(params, dict):
        params = {}

    try:
        base_tr = float(params.get("tr", 0.0001))
    except Exception:
        base_tr = 0.0001

    new_tr = base_tr * 10.0
    params["tr"] = new_tr

    # fix im Scene schreiben
    scene["bootstrap_params"] = dict(params)
    scene["kaiserlich_threshold_tr"] = float(new_tr)
