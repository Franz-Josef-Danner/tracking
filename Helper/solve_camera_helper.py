# Helper/solve_camera_helper.py (Blender 4.4.3)
import bpy
from bpy.types import Operator

class CLIP_OT_watch_solve(bpy.types.Operator):
    bl_idname = "clip.watch_solve"
    bl_label = "Watch Camera Solve"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        scene = context.scene
        scene["solve_status"] = "pending"
        scene["solve_error"] = -1.0

        # Owner zur späteren Abmeldung
        owner = object()
        self._owner = owner

        # Freie Funktion (Closure), KEINE gebundene Methode:
        def _notify(*_args):
            # In Timer verlagern, um UI-Kontext-Probleme zu vermeiden
            def _finish():
                # Clip robust holen
                area = getattr(context, "area", None)
                space = getattr(context, "space_data", None)
                clip = getattr(space, "clip", None)
                if clip is None:
                    # versuche irgendeinen CLIP_EDITOR im Screen
                    scr = getattr(context, "screen", None)
                    if scr:
                        for a in scr.areas:
                            if a.type == "CLIP_EDITOR":
                                sp = a.spaces.active
                                clip = getattr(sp, "clip", None)
                                if clip:
                                    break

                rec = None
                try:
                    rec = clip.tracking.objects.active.reconstruction if (clip and clip.tracking and clip.tracking.objects) else None
                except Exception:
                    rec = None

                avg = getattr(rec, "average_error", None) if rec else None
                rec = None
                try:
                    rec = clip.tracking.objects.active.reconstruction if (clip and clip.tracking and clip.tracking.objects) else None
                except Exception:
                    rec = None
                
                if rec and getattr(rec, "is_valid", False):
                    avg = getattr(rec, "average_error", None)
                    scene["solve_status"] = "done"
                    if avg is not None:
                        scene["solve_error"] = float(avg)
                    try:
                        bpy.msgbus.clear_by_owner(owner)
                    except Exception:
                        pass
                    return None  # fertig
                else:
                    # noch nicht valide – in 0.2 s erneut prüfen
                    return 0.2


                try:
                    bpy.msgbus.clear_by_owner(owner)
                except Exception:
                    pass
                return None

            bpy.app.timers.register(_finish, first_interval=0.0)

        # Subscriptions
        try:
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "is_valid"),
                owner=owner,
                args=(),
                notify=_notify,   # <- freie Funktion
            )
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "average_error"),
                owner=owner,
                args=(),
                notify=_notify,   # <- freie Funktion
            )
        except Exception as ex:
            self.report({'WARNING'}, f"Msgbus-Subscribe fehlgeschlagen: {ex}. Fallback: Polling in main.")
            # Markiere Fallback
            scene["solve_watch_fallback"] = True

        # Solve starten – nutzt deinen Helper (richtiger Kontext/Override)
        res = bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
        if res not in ({'FINISHED'}, {'RUNNING_MODAL'}):
            self.report({'ERROR'}, f"Camera Solve Start fehlgeschlagen: {res}")
            try:
                bpy.msgbus.clear_by_owner(owner)
            except Exception:
                pass
            return {'CANCELLED'}

        return {'FINISHED'}


def _find_clip_context(context: bpy.types.Context):
    """Finde (area, region, space) des CLIP_EDITOR, sonst (None, None, None)."""
    area = getattr(context, "area", None)
    if area and area.type == "CLIP_EDITOR":
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space = area.spaces.active
        if region and space:
            return area, region, space

    screen = getattr(context, "screen", None)
    if not screen:
        return None, None, None

    for a in screen.areas:
        if a.type == "CLIP_EDITOR":
            region = next((r for r in a.regions if r.type == "WINDOW"), None)
            if region:
                return a, region, a.spaces.active
    return None, None, None


def _build_override(context):
    """Nur die UI-Schlüssel für temp_override vorbereiten (kein window/screen!)."""
    area, region, space = _find_clip_context(context)
    if not (area and region and space and getattr(space, "clip", None)):
        return None
    return {"area": area, "region": region, "space_data": space}


class CLIP_OT_solve_camera_helper(Operator):
    """Startet den internen Kamera-Solver mit INVOKE_DEFAULT im korrekten Kontext."""
    bl_idname = "clip.solve_camera_helper"
    bl_label = "Solve Camera (Helper)"
    bl_options = {"INTERNAL"}  # UNDO optional

    def invoke(self, context, event):
        override = _build_override(context)
        if not override:
            self.report({"ERROR"}, "CLIP_EDITOR/Clip-Kontext fehlt. Clip Editor öffnen und Clip laden.")
            return {"CANCELLED"}

        # 1) Versuche INVOKE_DEFAULT mit gültigem UI-Kontext
        try:
            with context.temp_override(**override):
                result = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            if result != {"FINISHED"}:
                self.report({"WARNING"}, f"Kamera-Solve (INVOKE_DEFAULT): {result}")
        except RuntimeError as ex:
            # 2) Fallback EXEC_DEFAULT im selben Override
            self.report({"WARNING"}, f"INVOCATION fehlgeschlagen ({ex}). Fallback EXEC_DEFAULT …")
            try:
                with context.temp_override(**override):
                    result = bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                if result != {"FINISHED"}:
                    self.report({"ERROR"}, f"Kamera-Solve (EXEC_DEFAULT): {result}")
                    return {"CANCELLED"}
            except Exception as ex2:
                self.report({"ERROR"}, f"Kamera-Solve fehlgeschlagen: {ex2}")
                return {"CANCELLED"}

        # UI-Refresh (best effort)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
        return {"FINISHED"}


# --- Register Boilerplate ---
_classes = (CLIP_OT_solve_camera_helper, CLIP_OT_watch_solve)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
