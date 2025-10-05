"""Marker-Größen Verarbeitung.

Setzt globale Defaults im Tracking-Kontext für neu erstellte Marker.
"""
from __future__ import annotations

import bpy


def apply_marker_size(pz: int, sz: int):
    print(f"[Kaiserlich Tracker][MARKER_SIZE] Set pattern={pz} search={sz}")
    clip = _get_active_clip(bpy.context)
    if clip is None:
        return {'CANCELLED'}
    tracking = clip.tracking
    settings = tracking.settings
    # Blender interne Props: default_pattern_size / default_search_size
    try:
        settings.default_pattern_size = int(pz)
        settings.default_search_size = int(sz)
    except Exception as e:  # noqa: BLE001
        print(f"[Kaiserlich Tracker][MARKER_SIZE][ERROR] {e}")
        return {'CANCELLED'}
    return {'FINISHED'}


def _get_active_clip(context):
    space = getattr(context, 'space_data', None)
    if space and space.type == 'CLIP_EDITOR':
        return space.clip
    return None

