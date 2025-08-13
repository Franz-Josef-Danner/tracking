# Helper/jump_to_frame.py

import bpy
import json
from .detect import run_detect_adaptive

__all__ = ("jump_to_frame_helper", "run_jump_to_frame")

def _clip_override(context):
    win = context.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


def _resolve_target_frame(context, explicit_target: int | None) -> int | None:
    if explicit_target is not None and explicit_target >= 0:
        return int(explicit_target)
    scene = context.scene
    tf = scene.get("goto_frame")
    return int(tf) if tf is not None else None


def _get_visited_frames(scene) -> list[int]:
    raw = scene.get("visited_frames_json", "[]")
    try:
        data = json.loads(raw)
        return [int(x) for x in data if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()]
    except Exception:
        return []


def _store_visited_frame(scene, frame: int) -> bool:
    frames = _get_visited_frames(scene)
    is_duplicate = int(frame) in frames
    if not is_duplicate:
        frames.append(int(frame))
        scene["visited_frames_json"] = json.dumps(frames)
        print(f"[GotoFrame] Persistiert: visited_frames_json → {scene['visited_frames_json']}")
    else:
        print(f"[GotoFrame] Duplikat erkannt (Frame {frame}) – Helper wird ausgelöst.")
    return is_duplicate


def jump_to_frame_helper(context, target_frame: int | None = None):
    """
    Reiner Helper. Setzt den Playhead, triggert bei Duplikat den Marker-Adapt-Helper
    und ruft anschließend detect_once auf dem Ziel-Frame auf.
    Rückgabe: {'FINISHED'} oder {'CANCELLED'}
    """
    # Ziel-Frame auflösen
    target = _resolve_target_frame(context, target_frame if (target_frame is not None and target_frame >= 0) else None)
    if target is None:
        print("[GotoFrame] Kein Ziel-Frame gefunden.")
        return {'CANCELLED'}

    # Frame speichern + Duplikat-Check
    is_dup = _store_visited_frame(context.scene, int(target))
    if is_dup:
        try:
            bpy.ops.clip.marker_adapt_boost('EXEC_DEFAULT')
        except Exception as ex:
            # identisches Verhalten: Fehler loggen, aber nicht crashen
            print(f"Error: Marker-Adapt-Helper fehlgeschlagen: {ex}")

    # Playhead setzen + DETECT auslösen
    ovr = _clip_override(context)
    try:
        if ovr:
            with context.temp_override(**ovr):
                context.scene.frame_current = int(target)
                print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (mit Override).")
                # Detect direkt starten; Frame explizit übergeben (robust ggü. UI-Latenz)
                res = bpy.ops.clip.detect_once('INVOKE_DEFAULT', frame=int(target))
        else:
            context.scene.frame_current = int(target)
            print(f"[GotoFrame] Playhead auf Frame {target} gesetzt (ohne Override).")
            res = bpy.ops.clip.detect_once('INVOKE_DEFAULT', frame=int(target))

        print(f"[GotoFrame] Übergabe an detect → {res}")
        return {'FINISHED'}

    except Exception as ex:
        msg = f"Übergabe an detect fehlgeschlagen: {ex}"
        print(f"Error: {msg}")
        return {'CANCELLED'}


def run_jump_to_frame(context, frame: int | None = None):
    """
    Thin-Wrapper für Kompatibilität mit bestehender Aufrufstelle.
    Vorher: bpy.ops.clip.jump_to_frame('EXEC_DEFAULT', target_frame=…)
    Jetzt:  run_jump_to_frame(context, frame=…)
    """
    return jump_to_frame_helper(context, target_frame=frame)
