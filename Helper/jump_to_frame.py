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


def _load_visited(scene):
    key = "visited_frames_json"
    try:
        arr = json.loads(scene.get(key, "[]"))
        if not isinstance(arr, list):
            arr = []
    except Exception:
        arr = []
    return arr


def _store_visited(scene, arr):
    scene["visited_frames_json"] = json.dumps(arr)
    print(f"[GotoFrame] persisted visited_frames: {arr}")


def _is_duplicate_and_update(scene, frame) -> bool:
    """
    Duplikatprüfung/Update NUR nach erfolgreichem Jump.
    """
    arr = _load_visited(scene)
    if frame in arr:
        return True
    arr.append(frame)
    _store_visited(scene, arr)
    return False


def jump_to_frame_helper(context, *, target_frame=None):
    """
    Policy-konform:
    1) Frame setzen und VALIDIEREN.
    2) Erst danach Duplikat prüfen/speichern.
    3) Bei Duplikat optional Marker-Adapt-Boost triggern.
    """
    f = _resolve_target_frame(context, explicit=target_frame)
    if f is None:
        print("[GotoFrame] Kein Ziel-Frame gefunden.")
        return {'CANCELLED'}

    # 1) Setzen & validieren
    try:
        context.scene.frame_set(int(f))
    except Exception as ex:
        print(f"[GotoFrame] frame_set({f}) Exception: {ex}")
        return {'CANCELLED'}

    if context.scene.frame_current != int(f):
        print(f"[GotoFrame] Validierung fehlgeschlagen: current={context.scene.frame_current}, expected={int(f)}")
        return {'CANCELLED'}

    # 2) Jetzt erst speichern/prüfen
    is_dup = _is_duplicate_and_update(context.scene, int(f))
    if is_dup:
        print(f"[GotoFrame] Duplikat erkannt (Frame {f}) – Helper wird ausgelöst.")
        try:
            from .marker_adapt_helper import run_marker_adapt_boost
            run_marker_adapt_boost(context)
        except Exception as ex:
            print(f"[MarkerAdapt] Boost fehlgeschlagen: {ex}")

    return {'FINISHED'}


def run_jump_to_frame(context, *, frame=None):
    return jump_to_frame_helper(context, target_frame=frame)
