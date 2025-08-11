# tracking-final/Helper/solve_camera_helper.py
import bpy

def _find_clip_context(context: bpy.types.Context):
    """Suche einen gültigen CLIP_EDITOR-Kontext (area, region, space_data)."""
    screen = context.screen
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    space = area.spaces.active
                    # safety: nur wenn wirklich ein Clip aktiv ist
                    if getattr(space, "clip", None):
                        return area, region, space
    return None, None, None


def solve_camera_helper(context: bpy.types.Context = None):
    """
    Programmatischer Helper: löst den Kamera-Solve via INVOKE_DEFAULT aus.
    Nutzt Context-Override, damit der Operator sicher im CLIP-Kontext läuft.
    """
    ctx = context or bpy.context
    area, region, space = _find_clip_context(ctx)

    try:
        if area and region and space:
            with bpy.context.temp_override(area=area, region=region, space_data=space):
                result = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        else:
            # Fallback: versuchen ohne Override (z. B. Headless/Test)
            result = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')

        print(f"[CameraSolve] Trigger result: {result}")
        return result
    except Exception as e:
        print(f"[CameraSolve] Fehler beim Auslösen: {e}")
        return {'CANCELLED'}


class CLIP_OT_solve_camera_helper(bpy.types.Operator):
    """Wrapper-Operator: ruft solve_camera im gültigen CLIP-Kontext auf."""
    bl_idname = "clip.solve_camera_helper"
    bl_label = "Solve Camera (Helper)"
    bl_description = "Startet den Kamera-Solve UI-konform mit Context-Override"
    bl_options = {'REGISTER', 'INTERNAL'}  # INTERNAL: nicht prominent im UI

    @classmethod
    def poll(cls, context):
        # Solve nur erlauben, wenn ein Clip plausibel verfügbar ist
        try:
            area, region, space = _find_clip_context(context)
            return bool(space and getattr(space, "clip", None))
        except Exception:
            return False

    def execute(self, context):
        # Falls direkt EXECUTE gerufen wird, trotzdem Solve durchführen
        res = solve_camera_helper(context)
        return {'FINISHED'} if res == {'FINISHED'} else {'CANCELLED'}

    def invoke(self, context, event):
        # Präferierter Pfad: INVOKE_DEFAULT für UI-Flow
        res = solve_camera_helper(context)
        return {'FINISHED'} if res == {'FINISHED'} else {'CANCELLED'}


# ---- Registrierungs-API ----
CLASSES = (CLIP_OT_solve_camera_helper,)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
