"""Marker-Größen Verarbeitung.

Setzt die Standard-Pattern- und Suchgrößen für neu anzulegende Tracks.
Hinweis: Blender speichert globale Tracking Settings unter clip.tracking.settings.
"""
from __future__ import annotations

import bpy


def apply_marker_size(pz: int, sz: int):
    clip = _get_active_clip(bpy.context)
    if clip is None:
        print("[Kaiserlich Tracker][MARKER_SIZE] Kein aktiver Clip.")
        return {'CANCELLED'}
    settings = clip.tracking.settings
    # Blender erwartet ints
    settings.default_pattern_size = int(pz)
    settings.default_search_size = int(sz)
    print(f"[Kaiserlich Tracker][MARKER_SIZE] pattern={settings.default_pattern_size} search={settings.default_search_size}")
    return {'FINISHED'}


def _get_active_clip(context):
    space = getattr(context, 'space_data', None)
    if space and space.type == 'CLIP_EDITOR':
        return space.clip
    return None
