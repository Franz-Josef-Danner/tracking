
# Helper/jump_to_frame.py
import bpy
import json

__all__ = ("run_jump_to_frame", "jump_to_frame_helper")

def _resolve_target_frame(context, explicit=None):
    if explicit is not None:
        try:
            f = int(explicit)
            if f >= 0:
                return f
        except Exception:
            pass
    try:
        f = int(context.scene.get("goto_frame", -1))
        return f if f >= 0 else None
    except Exception:
        return None

def _store_visited_frame(scene, frame):
    key = "visited_frames_json"
    try:
        arr = json.loads(scene.get(key, "[]"))
        if not isinstance(arr, list):
            arr = []
    except Exception:
        arr = []
    if frame in arr:
        return True
    arr.append(frame)
    scene[key] = json.dumps(arr)
    print(f"[GotoFrame] persisted visited_frames: {arr}")
    return False

def jump_to_frame_helper(context, *, target_frame=None):
    use_coord = bool(context.scene.get("orchestrator_active", False))
    f = _resolve_target_frame(context, explicit=target_frame)
    if f is None:
        print("[GotoFrame] Kein Ziel-Frame gefunden.")
        return {'CANCELLED'}

    is_dup = _store_visited_frame(context.scene, int(f))
    if is_dup:
        print(f"[GotoFrame] Duplikat erkannt (Frame {f}) – Helper wird ausgelöst.")
        try:
            from .marker_adapt_helper import run_marker_adapt_boost
            run_marker_adapt_boost(context)
        except Exception as ex:
            print(f"[MarkerAdapt] Boost fehlgeschlagen: {ex}")

    try:
        context.scene.frame_current = int(f)
    except Exception as ex:
        print(f"[GotoFrame] Frame-Setzen fehlgeschlagen: {ex}")

    return {'FINISHED'}

def run_jump_to_frame(context, *, frame=None):
    return jump_to_frame_helper(context, target_frame=frame)
