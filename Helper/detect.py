import bpy
from typing import Optional, Dict, Any


def detect_features(context, params: Dict[str, Any]):
    """Wrap für bpy.ops.clip.detect_features mit Parametern aus bootstrap.

    Erwartet Keys: ma (margin), md (min_distance), tr (threshold)
    """
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        return {'CANCELLED'}

    margin = params.get('ma', 16)
    min_distance = params.get('md', 120)
    threshold = params.get('tr', 0.5)
    pattern_size = int(params.get('pz', 21))  # fallback typische Standardgröße
    search_size = int(params.get('sz', pattern_size * 2))


    # Versuche die globalen Tracking Settings zu beeinflussen (optional, abhängig von Blender Version)
    clip = space.clip
    if clip:
        tracking = clip.tracking
        try:
            settings = tracking.settings
            # Einige Blender-Versionen verwenden pattern_size / search_size (oder search_size ist eine Eigenschaft von settings)
            if hasattr(settings, 'pattern_size'):
                settings.pattern_size = pattern_size
            if hasattr(settings, 'search_size'):
                settings.search_size = search_size
        except Exception:
            pass

    try:
        bpy.ops.clip.detect_features(
            placement='FRAME',
            margin=margin,
            threshold=threshold,
            min_distance=min_distance,
        )
    except Exception:
        return {'CANCELLED'}

    return {'FINISHED'}
