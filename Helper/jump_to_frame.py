# Helper/jump_to_frame.py
import bpy
import json

from .detect import run_detect_once

__all__ = ("run_jump_to_frame", "jump_to_frame_helper")

def _clip_override(context):
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

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
    """
    Führt eine JSON-Liste scene["visited_frames_json"].
    Gibt True zurück, wenn der Frame bereits vorhanden war (Duplikat).
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
        # +10% adapt
        try:
            from .marker_adapt_helper import run_marker_adapt_boost
            run_marker_adapt_boost(context)
        except Exception as ex:
            print(f"[MarkerAdapt] Boost fehlgeschlagen: {ex}")

    # Clip und Override organisieren
    ovr = _clip_override(context)

    # Clip aus Kontext oder Fallback
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

    # Im Override Clip + Mode setzen
    if ovr:
        try:
            with context.temp_override(**ovr):
                try:
                    ovr['space_data'].clip = clip
                except Exception:
                    pass
                try:
                    ovr['space_data'].mode = 'TRACKING'
                except Exception:
                    pass
        except Exception as ex:
            print(f"[GotoFrame] Override-Setzen fehlgeschlagen: {ex}")

    # Detect im GLEICHEN Kontext starten (run_detect_once kümmert sich um eigenen Override)
    try:
        res = run_detect_once(context, start_frame=int(f))
        print(f"[Jump] detect_once Result: {res}")
        return {'FINISHED'}
    except Exception as ex:
        print(f"[Jump] Übergabe an detect fehlgeschlagen: {ex}")
        return {'CANCELLED'}

def run_jump_to_frame(context, *, frame=None):
    """Wrapper für Abwärtskompatibilität."""
    return jump_to_frame_helper(context, target_frame=frame)
