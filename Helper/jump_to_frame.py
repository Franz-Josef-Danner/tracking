# Helper/jump_to_frame.py
import bpy
import json

from .detect import run_detect_once

__all__ = ("run_jump_to_frame", "jump_to_frame_helper")


def _resolve_target_frame(context, explicit=None):
    if explicit is not None:
        try:
            f = int(explicit)
            if f >= 0:
                return f
        except Exception:
            pass
    scene = context.scene
    if "goto_frame" in scene:
        try:
            f = int(scene["goto_frame"])
            if f >= 0:
                return f
        except Exception:
            pass
    return None


def _store_visited_frame(scene, frame):
    """Maintain a JSON list in scene['visited_frames_json'].
    Returns True if the frame was already present (duplicate).
    """
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
    # Ziel ermitteln
    f = _resolve_target_frame(context, explicit=target_frame)
    if f is None:
        print("[GotoFrame] Kein Ziel-Frame gefunden.")
        return {'CANCELLED'}

    scene = context.scene
    is_dup = _store_visited_frame(scene, int(f))
    if is_dup:
        print(f"[GotoFrame] Duplikat erkannt (Frame {f}) – Helper wird ausgelöst.")
        # adapt um +10% erhöhen (Bestandteil deiner bestehenden Logik)
        try:
            from .marker_adapt_helper import run_marker_adapt_boost
            run_marker_adapt_boost(context)
        except Exception as ex:
            print(f"[MarkerAdapt] Boost fehlgeschlagen: {ex}")

    # Clip aus aktuellem Space (kein Area-Switch in diesem Helper)
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip is None:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            clip = None

    if clip is None:
        print("[GotoFrame] Kein Clip verfügbar.")
        return {'CANCELLED'}

    # Frame setzen (Best Effort)
    try:
        context.scene.frame_current = int(f)
    except Exception as ex:
        print(f"[GotoFrame] Frame-Setzen fehlgeschlagen: {ex}")

    return {'FINISHED'}


def run_jump_to_frame(context, *, frame=None):
    """Wrapper for compatibility."""
    return jump_to_frame_helper(context, target_frame=frame)
