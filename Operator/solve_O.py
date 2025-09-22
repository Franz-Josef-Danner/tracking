import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
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
    tr = clip.tracking
    obj = None
    try:
        obj = tr.objects.active or (tr.objects[0] if len(tr.objects) else None)
    except Exception:
        obj = None
    tracks_col = obj.tracks if obj and getattr(obj, "tracks", None) else getattr(tr, "tracks", [])
    tracks = list(tracks_col)
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
    op_deleted = 0
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
                if not tracks_col.get(n):
                    op_deleted += 1
            except Exception:
                pass
    except Exception:
        op_deleted = 0
    deleted = op_deleted
    # Wenn der Operator nichts gelöscht hat, direkte API verwenden
    if deleted == 0:
        for t in victims:
            try:
                tracks_col.remove(t)
                deleted += 1
            except Exception:
                pass
    return {"deleted": int(deleted), "names": names}


def _resolve_clip(context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        try:
            clip = bpy.data.movieclips[0]
        except Exception:
            clip = None
    return clip


def _compute_avg_track_error(context) -> float | None:
    """Bildet den Mittelwert über alle Track.average_error (nur gültige, >=0, endlich).
    Bevorzugt das aktive Tracking-Objekt; fällt auf globale Tracks zurück.
    """
    clip = _resolve_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return None
    tr = clip.tracking
    try:
        obj = tr.objects.active or (tr.objects[0] if len(tr.objects) else None)
    except Exception:
        obj = None
    tracks = list(getattr(obj, "tracks", [])) if obj and getattr(obj, "tracks", None) else list(getattr(tr, "tracks", []))
    s = 0.0
    n = 0
    for t in tracks:
        try:
            if getattr(t, "mute", False):
                continue
            ev = float(getattr(t, "average_error", float("nan")))
            if ev == ev and ev >= 0.0 and ev != float("inf") and ev != float("-inf"):
                s += ev
                n += 1
        except Exception:
            pass
    if n == 0:
        return None
    return s / n


class CLIP_OT_solve_cycle(Operator):
    bl_idname = "clip.solve_cycle"
    bl_label = "Solve Cycle (1x Solve, modal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _t0: float = 0.0
    _timeout: float = 20.0
    _score: object = None
    _last_avg_error: float | None = None

    def _stop_timer(self, context):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def _finish(self, context, status: str, avg_error_val, del_info: dict):
        scn = context.scene
        # Telemetrie schreiben
        result = {
            "status": status,
            "score": self._score if isinstance(self._score, (int, float)) else _safe_for_scene(self._score),
            "avg_error": avg_error_val if isinstance(avg_error_val, (int, float)) else _safe_for_scene(avg_error_val),
        }
        try:
            scn["tco_last_solve_cycle"] = _safe_for_scene(result)
        except Exception:
            # Fallback-Primitive
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
        try:
            scn["tco_last_unreconstructed_cleanup"] = _safe_for_scene(del_info or {})
        except Exception:
            pass
        # Active-Flag auf False und Done-Zeitstempel setzen
        try:
            scn["tco_solve_active"] = False
            scn["tco_solve_done_ts"] = float(time.time())
        except Exception:
            pass
        self.report({'INFO'}, f"Solve-Cycle abgeschlossen: status={status} score={result['score']} avg_error={result['avg_error']}")
        self._stop_timer(context)
        return {'FINISHED'} if status == 'OK' else {'CANCELLED'}

    def invoke(self, context, event):
        scn = context.scene
        # Flags setzen
        try:
            scn["tco_solve_active"] = True
        except Exception:
            pass
        # Refine aus, Keyframe an
        _disable_solve_refine_flags(context)
        # Timeout laden
        try:
            self._timeout = float(scn.get("tco_solve_wait_timeout", 20.0))
        except Exception:
            self._timeout = 20.0
        # Solve starten (modal, UI‑Feedback via Blender)
        try:
            self._score = solve_camera_only(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Solve fehlgeschlagen: {exc}")
            return self._finish(context, "ERROR", avg_error_val=0.0, del_info={})
        # Timer starten und in Modal wechseln
        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        try:
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
        except Exception:
            self._timer = wm.event_timer_add(0.10)
        self._t0 = time.perf_counter()
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Solve gestartet – warte auf Rekonstruktion/Avg-Error …")
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Falls EXEC_DEFAULT ausgelöst wird, verhalte dich wie INVOKE_DEFAULT
        return self.invoke(context, None)

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        # UI/Deps aktualisieren + UI redraw pulse
        try:
            context.view_layer.update()
        except Exception:
            pass
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
        # Avg-Error aus Track.average_error bilden
        avg_error = _compute_avg_track_error(context)
        elapsed = time.perf_counter() - self._t0
        if isinstance(avg_error, (int, float)):
            self._last_avg_error = float(avg_error)
            # Cleanup unreconstructed und Abschluss
            del_info = _delete_unreconstructed_tracks(context)
            self.report({'INFO'}, f"Unreconstructed cleanup: deleted={int(del_info.get('deleted',0))}")
            return self._finish(context, "OK", avg_error_val=self._last_avg_error, del_info=del_info)
        if elapsed >= self._timeout:
            # Timeout: letzten gültigen Wert verwenden, sonst 0.0
            final_err = float(self._last_avg_error) if isinstance(self._last_avg_error, (int, float)) else 0.0
            if not isinstance(self._last_avg_error, (int, float)):
                self.report({'WARNING'}, "Avg-Error-Observe Timeout – fahre fort")
            del_info = _delete_unreconstructed_tracks(context)
            self.report({'INFO'}, f"Unreconstructed cleanup: deleted={int(del_info.get('deleted',0))}")
            return self._finish(context, "OK", avg_error_val=final_err, del_info=del_info)
        return {'RUNNING_MODAL'}


def register():
    bpy.utils.register_class(CLIP_OT_solve_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_cycle)
