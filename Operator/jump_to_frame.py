import bpy
import json
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
    return int(tf) if tf is not None else None

def _get_visited_frames(scene) -> list[int]:
    """Frames-Liste aus Szene lesen (JSON)."""
    raw = scene.get("visited_frames_json", "[]")
    try:
        data = json.loads(raw)
        # Absicherung auf int-Liste
        return [int(x) for x in data if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()]
    except Exception:
        return []

def _store_visited_frame(scene, frame: int) -> bool:
    """
    Speichert Frame in Szene, liefert True wenn es ein Duplikat war.
    Persistiert als JSON in scene['visited_frames_json'].
    """
    frames = _get_visited_frames(scene)
    is_duplicate = int(frame) in frames
    if not is_duplicate:
        frames.append(int(frame))
        scene["visited_frames_json"] = json.dumps(frames)
        print(f"[GotoFrame] Persistiert: visited_frames_json → {scene['visited_frames_json']}")
    else:
        print(f"[GotoFrame] Duplikat erkannt (Frame {frame}) – Helper wird ausgelöst.")
    return is_duplicate


class CLIP_OT_jump_to_frame(Operator):
    """Setzt den Playhead, protokolliert den Frame in der Szene und löst am Ende clip.main aus.
       Bei Duplikat triggert ein Helper die Erhöhung von scene['marker_adapt'] um +10%."""
    bl_idname = "clip.jump_to_frame"
    bl_label = "Jump to Frame"
    bl_options = {"INTERNAL", "REGISTER"}

    # -1 = aus Scene['goto_frame'] lesen
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

        # Persistenz + Duplikat-Check
        is_dup = _store_visited_frame(context.scene, int(target))
        if is_dup:
            try:
                # Helper zur Anpassung von marker_adapt auslösen
                bpy.ops.clip.Helper.marker_adapt_boost('EXEC_DEFAULT')
            except Exception as ex:
                self.report({'ERROR'}, f"Marker-Adapt-Helper fehlgeschlagen: {ex}")
                print(f"Error: Marker-Adapt-Helper fehlgeschlagen: {ex}")

        ovr = _clip_override(context)
        try:
            if ovr:
                with context.temp_override(**ovr):
                    context.scene.frame_current = int(target)
                    print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (mit Override).")
                    # --- nur am Schluss: main auslösen ---
                    res = bpy.ops.clip.main('INVOKE_DEFAULT')
            else:
                context.scene.frame_current = int(target)
                print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (ohne Override).")
                res = bpy.ops.clip.main('INVOKE_DEFAULT')

            print(f"[GotoFrame] Übergabe an main → {res}")
            return {'FINISHED'}

        except Exception as ex:
            msg = f"Übergabe an main fehlgeschlagen: {ex}"
            self.report({'ERROR'}, msg)
            print(f"Error: {msg}")
            return {'CANCELLED'}


__all__ = ("CLIP_OT_jump_to_frame", "run_jump_to_frame")

def run_jump_to_frame(context, frame: int | None = None):
    """Komfort-Aufruf; löst am Ende immer main aus."""
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
