# Operator/main.py
# -*- coding: utf-8 -*-

import bpy
from bpy.types import Operator

# Import für Registrierung/Verfügbarkeit (keine Logikänderung)
from .clean_error_tracks import CLIP_OT_clean_error_tracks  # noqa: F401
from ..Helper.solve_camera_helper import solve_camera_helper


# -----------------------------------------------------------
# Kontext-Helfer
# -----------------------------------------------------------

def _find_clip_editor_ctx(context):
    """Liefert (area, region, space) eines sichtbaren CLIP_EDITOR oder (None, None, None)."""
    win = context.window
    if not win or not win.screen:
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


# -----------------------------------------------------------
# Pipeline (synchron)
# -----------------------------------------------------------

def _run_pipeline(context):
    """
    Führt die bestehende Tracking/Cleanup-Pipeline aus.
      1) clean_error_tracks
      2) solve_camera_helper (neu) am Ende
    """
    area, region, space = _find_clip_editor_ctx(context)
    if not space or not getattr(space, "clip", None):
        raise RuntimeError("Kein aktiver CLIP_EDITOR mit Movie Clip gefunden.")
    clip = space.clip

    # 1) Error-/Segment-Cleanup
    try:
        print("[Main] Starte clean_error_tracks …")
        with context.temp_override(area=area, region=region, space_data=space, edit_movieclip=clip):
            try:
                bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT', verbose=True)
            except TypeError:
                bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT')
        print("[Main] clean_error_tracks abgeschlossen.")
    except Exception as e:
        print(f"[Main] clean_error_tracks Exception: {e}")

    # 2) Kamera-Solve (neu)
    try:
        print("[Main] Starte Solve …")
        # Helper kapselt eigene temp_override-Aufrufe
        solve_res = solve_camera_helper(bpy.context)
        print(f"[Main] Solve done: {solve_res}")
    except Exception as e:
        print(f"[Main] Solve Exception: {e}")

    return {'FINISHED'}


# -----------------------------------------------------------
# Operatoren
# -----------------------------------------------------------

class CLIP_OT_pipeline_main(Operator):
    """Tracking-Pipeline (synchron) inkl. Solve am Ende."""
    bl_idname = "clip.pipeline_main"
    bl_label = "Pipeline Main"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _run_pipeline(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class CLIP_OT_tracking_pipeline(Operator):
    """Alias-Operator für vorhandene UI/Shortcuts."""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _run_pipeline(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class CLIP_OT_main(Operator):
    """Historischer Name – ruft dieselbe Pipeline auf."""
    bl_idname = "clip.main"
    bl_label = "Main"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _run_pipeline(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


# -----------------------------------------------------------
# Registration
# -----------------------------------------------------------

_CLASSES = (
    CLIP_OT_pipeline_main,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_main,
)

def register():
    for cls in _CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass  # bereits registriert

def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass
