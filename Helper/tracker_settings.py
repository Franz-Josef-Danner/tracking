# tracker_settings.py
import bpy

__all__ = ("apply_tracker_settings",)


def _resolve_clip_and_scene(context, clip=None, scene=None):
    """Robuste Auflösung von clip/scene aus Context – ohne UI-Seiteneffekte."""
    scn = scene or getattr(context, "scene", None)
    if clip:
        return clip, scn

    # Primär: aktiver CLIP_EDITOR
    space = getattr(context, "space_data", None)
    c = getattr(space, "clip", None) if space else None
    if c:
        return c, scn

    # Fallback: erster Clip der Datei (wenn vorhanden)
    try:
        for c in bpy.data.movieclips:
            return c, scn
    except Exception:
        pass

    return None, scn


def _clamp01(x: float) -> float:
    if not isinstance(x, (int, float)):
        return 0.75
    if x <= 0.0:
        return 1e-4
    if x > 1.0:
        return 1.0
    return float(x)


def _try_set(container, names, value):
    """Versucht der Reihe nach, ein Attribut in container oder dessen .solver zu `value` zu setzen.
    Gibt das tatsächlich verwendete Attribut zurück oder None.
    """
    for name in names:
        if hasattr(container, name):
            try:
                setattr(container, name, value)
                return name
            except Exception:
                continue
    sub = getattr(container, "solver", None)
    if sub:
        for name in names:
            if hasattr(sub, name):
                try:
                    setattr(sub, name, value)
                    return f"solver.{name}"
                except Exception:
                    continue
    return None

def apply_tracker_settings(context, *, clip=None, scene=None, log: bool = True) -> dict:
    """
    Setzt vordefinierte Tracking-Defaults abhängig von der Clip-Auflösung
    und initialisiert/aktualisiert scene['last_detection_threshold'].
    Triggert anschließend die Low-Marker-Logik via run_find_low_marker_frame.

    Zusätzlich werden einige Solver-Optionen auf False gesetzt, damit die
    Standard-Solver-Einstellungen erwartbar sind:
      - Tripod Motion
      - Keyframe Selection
      - Refine Focal Length
      - Refine Optical center (Principal Point)
      - Refine Radial Distortion
    """
    clip, scene = _resolve_clip_and_scene(context, clip=clip, scene=scene)
    if clip is None or scene is None:
        if log:
            pass
        return {"status": "cancelled", "reason": "no_clip_or_scene"}

    # Breite robust lesen
    width = int(clip.size[0]) if getattr(clip, "size", None) else 0

    ts = clip.tracking.settings

    # --- Defaults setzen (Altverhalten) ---
    ts.default_motion_model = 'Loc'
    ts.default_pattern_match = 'KEYFRAME'
    ts.use_default_normalization = True
    ts.default_weight = 1.0
    ts.default_correlation_min = 0.95
    ts.default_margin = 100
    ts.use_default_mask = False
    ts.use_default_red_channel = True
    ts.use_default_green_channel = True
    ts.use_default_blue_channel = True
    ts.use_default_brute = True

    # Auflösungsbasiert – Altformel: int(width / 100), min. 1
    pattern_size = max(1, int(width / 100)) if width > 0 else 8
    search_size = pattern_size * 2
    ts.default_pattern_size = pattern_size
    ts.default_search_size = search_size

    # Cleanup-Parameter aus Szene (mit Fallbacks)
    ts.clean_frames = getattr(scene, "frames_track", 20)
    ts.clean_error = getattr(scene, "error_track", 0.5)

    # Detection-Threshold aus Szene, sonst aus aktuellen Defaults
    try:
        default_min = float(getattr(ts, "default_correlation_min", 0.75))
    except Exception:
        default_min = 0.75

    try:
        det_thr = float(scene.get("last_detection_threshold", default_min))
    except Exception:
        det_thr = default_min

    det_thr = _clamp01(det_thr)
    scene["last_detection_threshold"] = float(det_thr)

    # --- Solver-Einstellungen: robuste Versuche mehrere mögliche Property-Namen ---
    solver_changes = {}

    # Tripod Motion
    tripod_name = _try_set(ts, ("use_tripod_motion", "use_tripod_solver", "use_tripod"), False)
    solver_changes['tripod'] = tripod_name

    # Keyframe Selection
    keyframe_name = _try_set(ts, ("use_keyframe_selection", "use_keyframes", "use_keyframe_selection_mode"), True)
    solver_changes['keyframe_selection'] = keyframe_name

    # Refine Focal Length
    refine_focal_name = _try_set(
        ts,
        (
            "refine_intrinsics_focal_length",
            "refine_focal_length",
            "refine_focal",
            "refine_focal_length_error",
        ),
        False,
    )
    solver_changes['refine_focal_length'] = refine_focal_name

    # Refine Optical center (Principal Point)
    refine_principal_name = _try_set_false(
        ts,
        (
            "refine_intrinsics_principal_point",
            "refine_principal_point",
            "refine_principal",
            "refine_principal_point_x",
        ),
    )
    solver_changes['refine_principal_point'] = refine_principal_name

    # Refine Radial Distortion
    refine_radial_name = _try_set_false(
        ts,
        (
            "refine_intrinsics_radial_distortion",
            "refine_radial_distortion",
            "refine_distortion",
            "refine_k1",
        ),
    )
    solver_changes['refine_radial_distortion'] = refine_radial_name

    if log:
        # Log welche Solver-Properties gesetzt wurden (falls vorhanden)
        for k, v in solver_changes.items():
            if v:
                pass
            else:
                pass

    return {
        "status": "ok",
        "clip": getattr(clip, "name", None),
        "width": width,
        "pattern_size": pattern_size,
        "search_size": search_size,
        "clean_frames": int(ts.clean_frames),
        "clean_error": float(ts.clean_error),
        "last_detection_threshold": float(scene["last_detection_threshold"]),
        "solver_changes": solver_changes,
    }
