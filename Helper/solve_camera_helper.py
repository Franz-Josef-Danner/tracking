# Helper/solve_camera_helper.py
import bpy
from bpy.types import Operator

def _find_clip_context(context: bpy.types.Context):
    """Ermittelt (area, region, space) für den CLIP_EDITOR. Gibt (None, None, None) zurück, falls nicht vorhanden."""
    # 1) Aktive Area bevorzugen
    area = getattr(context, "area", None)
    if area and area.type == "CLIP_EDITOR":
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space = area.spaces.active
        if region and space:
            return area, region, space

    # 2) Fallback: Screen scannen
    screen = getattr(context, "screen", None)
    if not screen:
        return None, None, None

    for a in screen.areas:
        if a.type == "CLIP_EDITOR":
            r = next((rg for rg in a.regions if rg.type == "WINDOW"), None)
            if r:
                return a, r, a.spaces.active
    return None, None, None


def _build_override(context):
    """Context-Override für CLIP_EDITOR erstellen. None bei Nichterfolg."""
    area, region, space = _find_clip_context(context)
    if not (area and region and space and getattr(space, "clip", None)):
        return None
    # Wichtig: KEIN window/screen in Operator-Override übergeben.
    return {"area": area, "region": region, "space_data": space}


class CLIP_OT_solve_camera_helper(Operator):
    """Löst den internen Kamera-Solver aus (INVOCATION), mit sauberem CLIP_CONTEXT."""
    bl_idname = "clip.solve_camera_helper"
    bl_label = "Solve Camera (Helper)"
    bl_options = {"INTERNAL", "UNDO"}  # UNDO optional – je nach Pipeline

    def invoke(self, context, event):
        override = _build_override(context)
        if not override:
            self.report(
                {"ERROR"},
                "CLIP_EDITOR/Clip-Kontext nicht verfügbar. Öffne den Clip Editor und lade einen Clip."
            )
            return {"CANCELLED"}

        # Primär: INVOKE_DEFAULT – öffnet ggf. Operator-UI/Dialoge
        def _build_override(context):
            """Context-Override für CLIP_EDITOR erstellen. None bei Nichterfolg."""
            area, region, space = _find_clip_context(context)
            if not (area and region and space and getattr(space, "clip", None)):
                return None
            # Wichtig: KEIN window/screen in Operator-Override übergeben.
            return {"area": area, "region": region, "space_data": space}
        
                # Leichtes UI-Refresh für sofortiges Feedback
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except Exception:
                    pass
        
                return {"FINISHED"}


# Modul-API für __init__.py
_classes = (CLIP_OT_solve_camera_helper,)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
