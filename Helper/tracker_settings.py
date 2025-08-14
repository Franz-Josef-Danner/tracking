# tracker_settings.py
import bpy
from .find_low_marker_frame import run_find_low_marker_frame

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


def apply_tracker_settings(context, *, clip=None, scene=None, log: bool = True) -> dict:
    """
    Setzt vordefinierte Tracking-Defaults abhängig von der Clip-Auflösung
    und initialisiert/aktualisiert scene['last_detection_threshold'].
    Triggert anschließend die Low-Marker-Logik via run_find_low_marker_frame.
    """
    clip, scene = _resolve_clip_and_scene(context, clip=clip, scene=scene)
    if clip is None or scene is None:
        if log:
            print("[TrackerSettings] Abbruch: Kein Clip oder Scene im Kontext.")
        return {"status": "cancelled", "reason": "no_clip_or_scene"}

    # Breite robust lesen
    width = int(clip.size[0]) if getattr(clip, "size", None) else 0

    ts = clip.tracking.settings

    # --- Defaults setzen (Altverhalten) ---
    ts.default_motion_model = 'Loc'
    ts.default_pattern_match = 'KEYFRAME'
    ts.use_default_normalization = True
    ts.default_weight = 1.0
    ts.default_correlation_min = 0.9
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

    if log:
        print(
            "[TrackerSettings] Defaults angewendet | "
            f"clip={clip.name!r}, width={width}, pattern={pattern_size}, search={search_size}, "
            f"clean_frames={ts.clean_frames}, clean_error={ts.clean_error}, "
            f"last_detection_threshold={scene['last_detection_threshold']:.6f}"
        )

    # ZWINGEND: Low-Marker-Pipeline anstoßen
    try:
        # use_scene_basis=True => nutzt scene['marker_basis']/ähnliche Keys, falls vorhanden
        run_find_low_marker_frame(context, use_scene_basis=True)
    except TypeError as ex:
        # Fallback für ältere Signatur ohne Keyword
        if log:
            print(f"[TrackerSettings] run_find_low_marker_frame(use_scene_basis=…) nicht unterstützt ({ex}), "
                  "starte ohne Keyword.")
        try:
            run_find_low_marker_frame(context)
        except Exception as ex2:
            if log:
                print(f"[TrackerSettings] Übergabe an find_low_marker_frame fehlgeschlagen: {ex2}")
    except Exception as ex:
        if log:
            print(f"[TrackerSettings] Übergabe an find_low_marker_frame fehlgeschlagen: {ex}")

    return {
        "status": "ok",
        "clip": getattr(clip, "name", None),
        "width": width,
        "pattern_size": pattern_size,
        "search_size": search_size,
        "clean_frames": int(ts.clean_frames),
        "clean_error": float(ts.clean_error),
        "last_detection_threshold": float(scene["last_detection_threshold"]),
    }
