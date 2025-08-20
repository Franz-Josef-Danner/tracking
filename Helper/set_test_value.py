import bpy
from typing import Any, Dict, Optional


def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Aktiven MovieClip robust ermitteln (CLIP_EDITOR bevorzugen)."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == 'CLIP_EDITOR':
        clip = getattr(space, "clip", None)
        if clip:
            return clip

    # Fallback: erster vorhandener Clip
    for c in bpy.data.movieclips:
        return c
    return None


def _safe_set(obj: Any, attr: str, value: Any, report: Dict[str, Any]) -> None:
    """setattr mit Attributprüfung: trägt Erfolg/Misserfolg in report ein."""
    if hasattr(obj, attr):
        try:
            setattr(obj, attr, value)
            report["applied"][attr] = value
        except Exception as ex:
            report["failed"][attr] = f"set failed: {ex!s}"
    else:
        report["missing"].append(attr)


def apply_tracker_settings(
    context: bpy.types.Context,
    *,
    default_motion_model: str = 'Loc',
    default_pattern_match: str = 'KEYFRAME',
    use_default_normalization: bool = True,
    default_weight: float = 1.0,
    default_correlation_min: float = 0.90,
    default_margin: int = 100,
    use_default_mask: bool = False,
    use_default_red_channel: bool = True,
    use_default_green_channel: bool = True,
    use_default_blue_channel: bool = True,
    use_default_brute: bool = True,
    sync_detect_threshold: bool = True,
) -> Dict[str, Any]:
    """
    Setzt die gewünschten Default-Tracker-Einstellungen auf dem aktiven MovieClip.
    Rückgabe enthält 'applied', 'missing', 'failed' zur Diagnose.
    """
    report: Dict[str, Any] = {"applied": {}, "missing": [], "failed": {}}

    clip = _get_active_clip(context)
    if not clip:
        report["failed"]["__clip__"] = "kein MovieClip gefunden"
        return report

    ts = clip.tracking.settings

    # Vorgabewerte setzen (nur falls Attribut existiert)
    _safe_set(ts, "default_motion_model", default_motion_model, report)
    _safe_set(ts, "default_pattern_match", default_pattern_match, report)
    _safe_set(ts, "use_default_normalization", use_default_normalization, report)
    _safe_set(ts, "default_weight", float(default_weight), report)
    _safe_set(ts, "default_correlation_min", float(default_correlation_min), report)
    _safe_set(ts, "default_margin", int(default_margin), report)
    _safe_set(ts, "use_default_mask", use_default_mask, report)
    _safe_set(ts, "use_default_red_channel", use_default_red_channel, report)
    _safe_set(ts, "use_default_green_channel", use_default_green_channel, report)
    _safe_set(ts, "use_default_blue_channel", use_default_blue_channel, report)

    # Manche Blender-Versionen unterscheiden 'use_default_brute' vs. 'use_brute'
    if hasattr(ts, "use_default_brute"):
        _safe_set(ts, "use_default_brute", use_default_brute, report)
    elif hasattr(ts, "use_brute"):
        _safe_set(ts, "use_brute", use_default_brute, report)
    else:
        report["missing"].append("use_default_brute/use_brute")

    # Optional: Detect-Helper mit der neuen Korrelation synchronisieren
    # (wird u. a. in detect.run_detect_once als Startschwelle genutzt)
    if sync_detect_threshold:
        try:
            context.scene["last_detection_threshold"] = float(default_correlation_min)
            report["applied"]["scene.last_detection_threshold"] = float(default_correlation_min)
        except Exception as ex:
            report["failed"]["scene.last_detection_threshold"] = f"set failed: {ex!s}"

    return report


set_test_value(context.scene, apply_settings=True, context=context)
    scene: bpy.types.Scene,
    *,
    apply_settings: bool = True,
    context: Optional[bpy.types.Context] = None,
    basis_divisor: float = 3.0,
    corridor: float = 0.10,
) -> Optional[int]:
    """
    Erweitert: Berechnet Marker-Korridorwerte **und** setzt (optional) die Tracker-Defaults.
    - marker_adapt = (marker_basis / basis_divisor)
    - marker_min/max = ± corridor
    Gibt marker_adapt zurück oder None, wenn marker_basis fehlt.
    """
    marker_basis = getattr(scene, "marker_frame", None)
    if marker_basis is None:
        return None

    marker_plus = float(marker_basis) / float(basis_divisor)
    marker_adapt = int(round(marker_plus))

    max_marker = int(round(marker_adapt * (1.0 + corridor)))
    min_marker = int(round(max(1, marker_adapt * (1.0 - corridor))))

    scene["marker_adapt"] = int(marker_adapt)
    scene["marker_max"] = int(max_marker)
    scene["marker_min"] = int(min_marker)
    scene["marker_basis"] = int(marker_basis)

    # Optional die geforderten Tracking-Settings setzen
    if apply_settings:
        ctx = context or bpy.context
        apply_tracker_settings(ctx)

    return int(marker_adapt)
