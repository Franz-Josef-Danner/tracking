# Operator/main.py
# -*- coding: utf-8 -*-

import bpy
from bpy.types import Operator

# Bestehende Operatoren / Helper, die es im Add-on bereits gibt
# (wichtig: wir rufen nur, was schon existiert)
from .clean_error_tracks import CLIP_OT_clean_error_tracks  # nur für Registrierungssicherheit
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


def _override_for_clip(context):
    """Erstellt ein Override-Dict für Clip-Operatoren oder None."""
    area, region, space = _find_clip_editor_ctx(context)
    if not space or not getattr(space, "clip", None):
        return None
    ov = context.copy()
    ov.update({
        "area": area,
        "region": region,
        "space_data": space,
        "edit_movieclip": space.clip,
    })
    return ov


# -----------------------------------------------------------
# Pipeline (synchron)
# -----------------------------------------------------------

def _run_pipeline(context):
    """
    Führt die bestehende Tracking/Cleanup-Pipeline aus.
    Minimal-invasive Orchestrierung:
      1) Clean-Error-Tracks (ruft intern Grid/Short-Segment/Split-Trim)
      2) Kamera-Solve per Helper (am Ende)
    """
    override = _override_for_clip(context)
    if override is None:
        raise RuntimeError("Kein aktiver CLIP_EDITOR mit Movie Clip gefunden.")

    # 1) Error-/Segment-Cleanup
    #    Hinweis: wir nutzen denselben Kontext wie die UI, keine Modalität.
    try:
        print("[Main] Starte clean_error_tracks …")
        # Übergibt 'verbose' nur, wenn die Signatur es vorsieht; robust mit **kwargs
        bpy.ops.clip.clean_error_tracks(override, 'EXEC_DEFAULT', verbose=True)
        print("[Main] clean_error_tracks abgeschlossen.")
    except TypeError:
        # Falls ältere Signatur ohne 'verbose'
        bpy.ops.clip.clean_error_tracks(override, 'EXEC_DEFAULT')
        print("[Main] clean_error_tracks abgeschlossen. (ohne verbose)")
    except Exception as e:
        print(f"[Main] clean_error_tracks Exception: {e}")

    # 2) Kamera-Solve (neu)
    try:
        print("[Main] Starte Solve …")
        solve_res = solve_camera_helper(bpy.context)
        print(f"[Main] Solve done: {solve_res}")
    except Exception as e:
        print(f"[Main] Solve Exception: {e}")

    return {'FINISHED'}


# -----------------------------------------------------------
# Operatoren (mehrere Namen für maximale Kompatibilität)
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
            # Bereits registriert (z. B. beim Hot-Reload)
            pass

def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass
