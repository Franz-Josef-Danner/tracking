# Helper/get_clip_context.py
# ------------------------------------------------------------
# Liefert ein gültiges Kontext-Override für den Movie Clip Editor.
# Erkennt aktive Bereiche, Fallback über alle Fenster, robust gegen None.
# ------------------------------------------------------------

import bpy
from typing import Optional, Dict, Any


def get_clip_context() -> Optional[Dict[str, Any]]:
    """
    Gibt ein valides Kontext-Override-Dictionary für bpy.ops.clip.* zurück.
    Wird kein Clip-Editor gefunden, gibt None zurück.
    """
    # 1. Prüfe zuerst, ob der aktuelle Bereich bereits ein Clip-Editor ist
    area = getattr(bpy.context, "area", None)
    if area and area.type == "CLIP_EDITOR":
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region:
            return {
                "window": bpy.context.window,
                "screen": bpy.context.screen,
                "area": area,
                "region": region,
                "space_data": area.spaces.active,
            }

    # 2. Fallback: Suche in allen Fenstern und Areas
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region:
                    return {
                        "window": window,
                        "screen": screen,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }

    # 3. Kein gültiger Clip-Editor gefunden
    return None
