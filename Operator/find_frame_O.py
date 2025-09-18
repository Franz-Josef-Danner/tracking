import bpy
from bpy.types import Operator

# Importiere die bestehenden Helper-Funktionen
try:
    from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
    from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
except Exception:
    # Fallbacks für alternative Modul-Layouts
    from .find_low_marker_frame import run_find_low_marker_frame  # type: ignore
    from .jump_to_frame import run_jump_to_frame  # type: ignore


class CLIP_OT_find_low_and_jump(Operator):
    """Finde den Low‑Marker‑Frame und springe dorthin. Ergebnis in Scene speichern."""
    bl_idname = "clip.find_low_and_jump"
    bl_label = "Find Low & Jump"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        scn = context.scene
        result = {"status": "FAILED"}
        try:
            # 1) Low‑Marker‑Frame suchen
            r_find = run_find_low_marker_frame(context)
            status = str(r_find.get("status", ""))
            if status != "FOUND":
                result = {"status": status or "NONE", "find": r_find}
                scn["tco_last_findlowjump"] = result  # type: ignore
                if status == "NONE":
                    self.report({'INFO'}, "Kein Low‑Marker‑Frame gefunden")
                    return {'FINISHED'}
                self.report({'WARNING'}, f"FindLow fehlgeschlagen: {r_find}")
                return {'CANCELLED'}

            frame = int(r_find.get("frame", 1))

            # 2) Sprung durchführen
            r_jump = run_jump_to_frame(context, frame=frame, repeat_map={})
            if str(r_jump.get("status", "")) != "OK":
                result = {"status": "JUMP_FAILED", "find": r_find, "jump": r_jump}
                scn["tco_last_findlowjump"] = result  # type: ignore
                self.report({'WARNING'}, f"Jump fehlgeschlagen: {r_jump}")
                return {'CANCELLED'}

            result = {
                "status": "OK",
                "frame": frame,
                "repeat_count": int(r_jump.get("repeat_count", 0)),
                "find": r_find,
                "jump": r_jump,
            }
            scn["tco_last_findlowjump"] = result  # type: ignore
            self.report({'INFO'}, f"FindLow+Jump: f{frame} (repeat={result['repeat_count']})")
            return {'FINISHED'}
        except Exception as exc:
            result = {"status": "EXCEPTION", "error": str(exc)}
            try:
                scn["tco_last_findlowjump"] = result  # type: ignore
            except Exception:
                pass
            self.report({'ERROR'}, f"FindLow+Jump Ausnahme: {exc}")
            return {'CANCELLED'}


def register():
    try:
        bpy.utils.register_class(CLP_OT_find_low_and_jump)  # type: ignore
    except Exception:
        bpy.utils.register_class(CLIP_OT_find_low_and_jump)


def unregister():
    try:
        bpy.utils.unregister_class(CLP_OT_find_low_and_jump)  # type: ignore
    except Exception:
        try:
            bpy.utils.unregister_class(CLP_OT_find_low_and_jump)
        except Exception:
            pass
