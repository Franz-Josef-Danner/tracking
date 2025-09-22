import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error, run_reduce_error_tracks
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
    """Deaktiviert explizit alle Solve‑Refine‑Checkboxen und Keyframe‑Selektion."""
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
        # Keyframe-Selection aus
        try:
            if hasattr(tr, "settings") and hasattr(tr.settings, "use_keyframe_selection"):
                tr.settings.use_keyframe_selection = True
        except Exception:
            pass
        # Refine‑Flags aus
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


class CLIP_OT_solve_cycle(Operator):
    bl_idname = "clip.solve_cycle"
    bl_label = "Solve Cycle (1x Solve)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        # 0. Refine/Keyframe deaktivieren
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
        # 3. Ggf. Cleanup anstoßen (avg_error > error_track)
        try:
            thr = float(getattr(scn, "error_track", 2.0) or 2.0)
        except Exception:
            thr = 2.0
        reduce_info = None
        if isinstance(avg_error, (int, float)) and float(avg_error) > float(thr):
            try:
                max_del = max(1, int(round(float(avg_error) * 2.0)))
            except Exception:
                max_del = 1
            try:
                reduce_info = run_reduce_error_tracks(context, max_to_delete=int(max_del))
                try:
                    scn["tco_last_reduce_pass"] = _safe_for_scene({
                        "avg_error": float(avg_error),
                        "threshold": float(thr),
                        "max_to_delete": int(max_del),
                        "result": reduce_info,
                    })
                except Exception:
                    pass
                self.report({'INFO'}, f"ReduceErrorTracks: avg_error={avg_error:.3f} thr={thr:.3f} max_del={int(max_del)} deleted={int(reduce_info.get('deleted',0) if isinstance(reduce_info, dict) else 0)}")
            except Exception as exc:
                self.report({'WARNING'}, f"ReduceErrorTracks failed: {exc}")
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
