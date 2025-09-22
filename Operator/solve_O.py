import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error
import time


def _safe_for_scene(obj):
    """Konvertiert Werte in Blender-ID-kompatible Typen (int/float/str/bool/list/dict)."""
    # Primitive
    if isinstance(obj, (int, float, str, bool)):
        return obj
    # None → String oder 0.0
    if obj is None:
        return "None"
    # Sets/Tuples/Listen → Liste
    if isinstance(obj, (set, tuple, list)):
        return [ _safe_for_scene(v) for v in list(obj) ]
    # Dict → rekursiv säubern, Keys zu String
    if isinstance(obj, dict):
        return { str(k): _safe_for_scene(v) for k, v in obj.items() }
    # Versuche float‑Cast
    try:
        return float(obj)
    except Exception:
        pass
    # Fallback: Stringrepräsentation
    try:
        return str(obj)
    except Exception:
        return "<unsupported>"


def _disable_solve_refine_flags(context) -> None:
    """Deaktiviert Refine‑Checkboxen; Keyframe‑Selektion bleibt explizit AN (True)."""
    try:
        clip = getattr(context, "edit_movieclip", None)
        if not clip:
            clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not clip and bpy.data.movieclips:
            clip = bpy.data.movieclips[0]
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if not settings:
            return
        # Keyframe-Selection an (beibehalten wie gewünscht)
        try:
            if hasattr(tr, "settings") and hasattr(tr.settings, "use_keyframe_selection"):
                tr.settings.use_keyframe_selection = True
        except Exception:
            pass
        # Refine‑Flags AUS
        for attr in (
            "refine_intrinsics_focal_length",
            "refine_intrinsics_principal_point",
            "refine_intrinsics_radial_distortion",
            "refine_intrinsics_tangential_distortion",
        ):
            try:
                if hasattr(settings, attr):
                    setattr(settings, attr, False)
            except Exception:
                pass
        try:
            context.view_layer.update()
        except Exception:
            pass
    except Exception:
        pass


def _find_clip_editor_override():
    wm = getattr(bpy.context, "window_manager", None)
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if getattr(area, "type", "") != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}


def _delete_unreconstructed_tracks(context) -> dict:
    """Löscht alle Tracks ohne rekonstruierte 3D‑Position (has_bundle=False)."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        try:
            clip = bpy.data.movieclips[0]
        except Exception:
            clip = None
    if not clip or not getattr(clip, "tracking", None):
        return {"deleted": 0, "names": []}
    tracks = list(getattr(clip.tracking, "tracks", []))
    victims = [t for t in tracks if not bool(getattr(t, "has_bundle", False))]
    if not victims:
        return {"deleted": 0, "names": []}
    # Auswahl setzen
    try:
        for t in tracks:
            try:
                t.select = False
            except Exception:
                pass
        for t in victims:
            try:
                t.select = True
            except Exception:
                pass
    except Exception:
        pass
    deleted = 0
    names = [getattr(t, "name", "<noname>") for t in victims]
    # Operator mit Override ausführen
    try:
        override = _find_clip_editor_override()
        if override:
            with bpy.context.temp_override(**override):
                bpy.ops.clip.delete_track()
        else:
            bpy.ops.clip.delete_track()
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        # zählen, welche weg sind
        for n in names:
            try:
                if not clip.tracking.tracks.get(n):
                    deleted += 1
            except Exception:
                pass
    except Exception:
        # Fallback: direkte API
        for t in victims:
            try:
                clip.tracking.tracks.remove(t)
                deleted += 1
            except Exception:
                pass
    return {"deleted": int(deleted), "names": names}


class CLIP_OT_solve_cycle(Operator):
    bl_idname = "clip.solve_cycle"
    bl_label = "Solve Cycle (1x Solve)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        # 0. Refine aus, Keyframe an
        _disable_solve_refine_flags(context)
        # 1. Kamera-Solve ausführen
        try:
            score = solve_camera_only(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Solve fehlgeschlagen: {exc}")
            try:
                scn["tco_last_solve_cycle"] = _safe_for_scene({"status": "ERROR", "reason": str(exc)})
            except Exception:
                pass
            return {'CANCELLED'}
        # 2. Reprojection Error abfragen – kurz auf gültige Rekonstruktion warten
        avg_error = None
        for _ in range(40):  # ~2s
            try:
                avg_error = get_avg_reprojection_error(context)
                if isinstance(avg_error, (int, float)) and avg_error > 0.0:
                    break
            except Exception:
                pass
            time.sleep(0.05)
        # 3. Nicht rekonstruierte Tracks löschen
        del_info = _delete_unreconstructed_tracks(context)
        try:
            scn["tco_last_unreconstructed_cleanup"] = _safe_for_scene(del_info)
        except Exception:
            pass
        self.report({'INFO'}, f"Unreconstructed cleanup: deleted={int(del_info.get('deleted',0))}")
        # 4. Zusammenfassen (robust säubern)
        result = {
            "status": "OK",
            "score": score if isinstance(score, (int, float)) else _safe_for_scene(score),
            "avg_error": avg_error if isinstance(avg_error, (int, float)) else _safe_for_scene(avg_error),
        }
        try:
            scn["tco_last_solve_cycle"] = _safe_for_scene(result)
        except Exception:
            # Als Fallback einzelne Primitive setzen
            try:
                scn["tco_last_solve_status"] = str(result.get("status"))
            except Exception:
                pass
            try:
                scn["tco_last_solve_score"] = float(result.get("score") or 0.0)
            except Exception:
                pass
            try:
                ae = result.get("avg_error")
                scn["tco_last_solve_avg_error"] = float(ae) if isinstance(ae, (int, float)) else 0.0
            except Exception:
                pass
        self.report({'INFO'}, f"Solve-Cycle abgeschlossen: status=OK score={result['score']} avg_error={result['avg_error']}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_solve_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_cycle)
