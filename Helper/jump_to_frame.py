import bpy
import json

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
            from .marker_adapt_helper import run_marker_adapt_boost
            run_marker_adapt_boost(context)
        except Exception as ex:
            print(f"Error: Marker-Adapt-Helper fehlgeschlagen: {ex}")

    # Playhead setzen + DETECT auslösen
    ovr = _clip_override(context)

    # Sicherstellen, dass ein Clip im Kontext hängt
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip is None:
        try:
            clip = next(iter(bpy.data.movieclips))
        except StopIteration:
            print("[GotoFrame] Kein MovieClip im Blendfile vorhanden – Abbruch.")
            return {'CANCELLED'}

        # Clip in den CLIP_EDITOR hängen (falls UI-Kontext vorhanden)
        if ovr:
            try:
                with context.temp_override(**ovr):
                    ovr['space_data'].clip = clip
                    try:
                        ovr['space_data'].mode = 'TRACKING'
                    except Exception:
                        pass
                print(f"[GotoFrame] Fallback-Clip gesetzt: {clip.name}")
            except Exception as ex:
                print(f"[GotoFrame] Konnte Fallback-Clip nicht im UI setzen: {ex}")

    # Detect im (falls möglich) UI-Override starten, damit detect den Clip sieht
    try:
        from .detect import run_detect_once
        if ovr:
            with context.temp_override(**ovr):
                res = run_detect_once(context, start_frame=target)
        else:
            res = run_detect_once(context, start_frame=target)
        print(f"[Jump] detect_once Result: {res}")

# Automatisch Tracking starten, wenn Detect ok war
try:
    if isinstance(res, dict) and res.get("status") in {"success", "ok"}:
        # Modal-Operator starten (non-blocking), falls vorhanden
        try:
            bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
            print("[Jump] optimize_tracking_modal gestartet.")
        except Exception as _ex:
            # Fallback: direktes Vorwärts-Tracking anstoßen (modal)
            try:
                bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
                print("[Jump] Fallback: Vorwärts-Tracking gestartet.")
            except Exception as __ex:
                print(f"[Jump] Tracking-Start fehlgeschlagen: {__ex}")
except Exception as ex2:
    print(f"[Jump] Auto-Tracking Ausnahme: {ex2}")

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
