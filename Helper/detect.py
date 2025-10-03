import bpy
from typing import Optional, Dict, Any


def detect_features(context, params: Dict[str, Any]):
    """Wrap für bpy.ops.clip.detect_features mit Parametern aus bootstrap.

    Erwartet Keys: ma (margin), md (min_distance), tr (threshold)
    """
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] detect_features: Kein Clip Editor Kontext.")
        return {'CANCELLED'}

    margin = params.get('ma', 16)
    min_distance = params.get('md', 120)
    threshold = params.get('tr', 0.5)

    print(f"[Kaiserlich Tracker] detect_features -> margin={margin} min_distance={min_distance} threshold={threshold}")

    try:
        bpy.ops.clip.detect_features(
            placement='FRAME',
            margin=margin,
            threshold=threshold,
            min_distance=min_distance,
        )
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler bei detect_features: {e}")
        return {'CANCELLED'}

    return {'FINISHED'}
