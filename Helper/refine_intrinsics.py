# Helper/refine_intrinsics.py

import bpy
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _get_tracking_settings(clip: Optional[bpy.types.MovieClip] = None) -> Optional[bpy.types.MovieTrackingSettings]:
    """
    Liefert die MovieTrackingSettings des aktiven Clips oder des übergebenen Clips.
    Robust gegen fehlenden Context (z.B. Call aus Operator ohne CLIP_EDITOR Fokus).
    """
    # 1) Expliziter Clip
    if clip and getattr(clip, "tracking", None) and getattr(clip.tracking, "settings", None):
        return clip.tracking.settings

    # 2) Space-Clip im aktuellen Context
    space = getattr(bpy.context, "space_data", None)
    space_clip = getattr(space, "clip", None) if space and space.type == 'CLIP_EDITOR' else None
    if space_clip and getattr(space_clip, "tracking", None) and getattr(space_clip.tracking, "settings", None):
        return space_clip.tracking.settings

    # 3) Fallback: aktiver Clip über Tracking-Kontext (wenn vorhanden)
    # Hinweis: Viele Setups halten den Clip in bpy.data.movieclips[0] o.ä. – bewusst kein hartes Fallback.
    return None


def _set_refine_flags(settings: bpy.types.MovieTrackingSettings,
                      focal: bool, principal: bool, radial: bool) -> None:
    settings.refine_intrinsics_focal_length = focal
    settings.refine_intrinsics_principal_point = principal
    settings.refine_intrinsics_radial_distortion = radial


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refine_intrinsics_reset(clip: Optional[bpy.types.MovieClip] = None) -> bool:
    """
    Setzt alle Intrinsics-Refine-Flags auf False.
    Returns:
        True bei Erfolg, sonst False (kein gültiger Tracking-Context).
    """
    settings = _get_tracking_settings(clip)
    if not settings:
        return False
    _set_refine_flags(settings, focal=False, principal=False, radial=False)
    return True


def refine_intrinsics_focal_length_on(clip: Optional[bpy.types.MovieClip] = None) -> bool:
    """
    Aktiviert ausschließlich 'Refine focal length', alle anderen False.
    """
    settings = _get_tracking_settings(clip)
    if not settings:
        return False
    _set_refine_flags(settings, focal=True, principal=False, radial=False)
    return True


def refine_intrinsics_principal_point_on(clip: Optional[bpy.types.MovieClip] = None) -> bool:
    """
    Aktiviert ausschließlich 'Refine principal point', alle anderen False.
    """
    settings = _get_tracking_settings(clip)
    if not settings:
        return False
    _set_refine_flags(settings, focal=False, principal=True, radial=False)
    return True


def refine_intrinsics_radial_distortion_on(clip: Optional[bpy.types.MovieClip] = None) -> bool:
    """
    Aktiviert ausschließlich 'Refine radial distortion', alle anderen False.
    """
    settings = _get_tracking_settings(clip)
    if not settings:
        return False
    _set_refine_flags(settings, focal=False, principal=False, radial=True)
    return True
