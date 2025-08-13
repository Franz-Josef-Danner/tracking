import bpy
from bpy.types import Operator

def _clip_override(context):
    """Sicherer CLIP_EDITOR-Override."""
    win = context.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

def _resolve_target_frame(context, explicit_target: int) -> int | None:
    """Ermittelt den Ziel-Frame: bevorzugt Operator-Property, sonst Scene['goto_frame']."""
    if explicit_target is not None and explicit_target >= 0:
        return int(explicit_target)
    scene = context.scene
    tf = scene.get("goto_frame")
    return int(tf) if tf is not None and int(tf) >= 0 else None


class CLIP_OT_jump_to_frame(Operator):
    """Setzt den Playhead auf den Ziel-Frame und übergibt anschließend an main."""
    bl_idname = "clip.jump_to_frame"
    bl_label = "Jump to Frame"
    bl_options = {"INTERNAL", "REGISTER"}

    # Optional direkte Übergabe; -1 = verwende Scene['goto_frame']
    target_frame: bpy.props.IntProperty(
        name="Ziel-Frame",
        default=-1, min=-1,
        description="-1 = aus Scene['goto_frame'] lesen"
    )

    def execute(self, context):
        target = _resolve_target_frame(context, self.target_frame if self.target_frame >= 0 else None)
        if target is None:
            self.report({'WARNING'}, "[GotoFrame] Kein Ziel-Frame (weder Property noch Scene['goto_frame']).")
            return {'CANCELLED'}

        ovr = _clip_override(context)
        try:
            if ovr:
                with context.temp_override(**ovr):
                    context.scene.frame_current = int(target)
                    print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (mit Override).")
                    # --- Übergabe an main im selben gültigen Kontext ---
                    res = bpy.ops.clip.main('EXEC_DEFAULT')
                    print(f"[GotoFrame] Übergabe an main → {res}")
            else:
                # Fallback ohne Override – funktioniert, UI-Refresh ggf. verzögert
                context.scene.frame_current = int(target)
                print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (ohne Override).")
                res = bpy.ops.clip.main('EXEC_DEFAULT')
                print(f"[GotoFrame] Übergabe an main → {res}")

        except Exception as ex:
            self.report({'ERROR'}, f"Übergabe an main fehlgeschlagen: {ex}")
            return {'CANCELLED'}

        return {'FINISHED'}


# ---- Public API (komfortabler Aufruf aus Code) -------------------------------

__all__ = ("CLIP_OT_jump_to_frame", "run_jump_to_frame")

def run_jump_to_frame(context, frame: int | None = None):
    """
    Programmatischer Aufruf:
      - frame ist optional; wenn None, wird Scene['goto_frame'] genutzt.
      - Übergibt nach dem Sprung automatisch an clip.main.
    """
    if frame is not None and frame >= 0:
        return bpy.ops.clip.jump_to_frame('EXEC_DEFAULT', target_frame=int(frame))
    else:
        return bpy.ops.clip.jump_to_frame('EXEC_DEFAULT')


# Registration
classes = (CLIP_OT_jump_to_frame,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
