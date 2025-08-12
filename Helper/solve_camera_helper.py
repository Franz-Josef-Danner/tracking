# tracking-sauber/Helper/solve_camera_helper.py
import bpy
from bpy.types import Operator

__all__ = ("CLIP_OT_solve_camera_helper", "CLIP_OT_watch_solve")


# --------- UI-Kontext-Helfer (unverändert zur ursprünglichen Logik) ---------
def _find_clip_context(context: bpy.types.Context):
    """Finde (area, region, space) des CLIP_EDITOR, sonst (None, None, None)."""
    area = getattr(context, "area", None)
    if area and area.type == "CLIP_EDITOR":
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space = area.spaces.active
        if region and space:
            return area, region, space

    screen = getattr(context, "screen", None)
    if not screen:
        return None, None, None

    for a in screen.areas:
        if a.type == "CLIP_EDITOR":
            region = next((r for r in a.regions if r.type == "WINDOW"), None)
            if region:
                return a, region, a.spaces.active
    return None, None, None


def _build_override(context):
    """Nur die UI-Schlüssel für temp_override vorbereiten (kein window/screen!)."""
    area, region, space = _find_clip_context(context)
    if not (area and region and space and getattr(space, "clip", None)):
        return None
    return {"area": area, "region": region, "space_data": space}


# ---------------------- Solve-Helper (Original beibehalten) ------------------
class CLIP_OT_solve_camera_helper(Operator):
    """Startet den internen Kamera-Solver mit INVOKE_DEFAULT im korrekten Kontext."""
    bl_idname = "clip.solve_camera_helper"
    bl_label = "Solve Camera (Helper)"
    bl_options = {"INTERNAL"}  # UNDO optional

    def invoke(self, context, event):
        override = _build_override(context)
        if not override:
            self.report({"ERROR"}, "CLIP_EDITOR/Clip-Kontext fehlt. Clip Editor öffnen und Clip laden.")
            return {"CANCELLED"}

        # 1) Versuche INVOKE_DEFAULT mit gültigem UI-Kontext
        try:
            with context.temp_override(**override):
                result = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            if result != {"FINISHED"}:
                self.report({"WARNING"}, f"Kamera-Solve (INVOKE_DEFAULT): {result}")
        except RuntimeError as ex:
            # 2) Fallback EXEC_DEFAULT im selben Override
            self.report({"WARNING"}, f"INVOCATION fehlgeschlagen ({ex}). Fallback EXEC_DEFAULT …")
            try:
                with context.temp_override(**override):
                    result = bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                if result != {"FINISHED"}:
                    self.report({"ERROR"}, f"Kamera-Solve (EXEC_DEFAULT): {result}")
                    return {"CANCELLED"}
            except Exception as ex2:
                self.report({"ERROR"}, f"Kamera-Solve fehlgeschlagen: {ex2}")
                return {"CANCELLED"}

        # UI-Refresh (best effort)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
        return {"FINISHED"}


# -------------------- Solve beobachten + Clean (Erweiterung) -----------------
class CLIP_OT_watch_solve(bpy.types.Operator):
    bl_idname = "clip.watch_solve"
    bl_label = "Watch Camera Solve"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        scene = context.scene
        scene["solve_status"] = "pending"
        scene["solve_error"] = -1.0

        # --- Erweiterungs-Status (NEU, nicht invasiv) ---
        self._phase = 1                  # 1 = nach erstem Solve, 2 = nach Clean/zweitem Solve
        self._preclean_started = False
        scene["solve_error_after_clean"] = -1.0
        scene["preclean_marker_count"] = -1
        scene["postclean_marker_count"] = -1
        scene["marker_drop_detected"] = False
        # -------------------------------------------------

        # Owner zur späteren Abmeldung
        owner = object()
        self._owner = owner
        self._scheduled = False  # Guard gegen Mehrfach-Timer

        # -------- kleine Helfer ----------
        def _count_markers(clip):
            try:
                tracks = clip.tracking.objects.active.tracks
            except Exception:
                return 0
            total = 0
            for t in tracks:
                try:
                    total += len(t.markers)
                except Exception:
                    pass
            return total
        # ---------------------------------

        def _notify(*_args):
            if self._scheduled:
                return
            self._scheduled = True

            def _finish():
                # Clip robust holen
                space = getattr(context, "space_data", None)
                clip = getattr(space, "clip", None)
                if not clip:
                    scr = getattr(context, "screen", None)
                    if scr:
                        for a in scr.areas:
                            if a.type == "CLIP_EDITOR":
                                sp = a.spaces.active
                                clip = getattr(sp, "clip", None)
                                if clip:
                                    break

                # Rekonstruktion prüfen
                rec = None
                try:
                    rec = clip.tracking.objects.active.reconstruction if (clip and clip.tracking and clip.tracking.objects) else None
                except Exception:
                    rec = None

                if rec and getattr(rec, "is_valid", False):
                    avg = getattr(rec, "average_error", None)

                    # ---------------- PHASE 1 ----------------
                    if self._phase == 1:
                        scene["solve_status"] = "done"
                        if avg is not None:
                            scene["solve_error"] = float(avg)

                        if not self._preclean_started:
                            self._preclean_started = True

                            # Warten bis Track-Fehlerwerte verfügbar sind (alle 0,2s)
                            def _wait_errors_then_clean():
                                try:
                                    tracks = clip.tracking.objects.active.tracks
                                except Exception:
                                    return 0.2

                                # Stabiler öffentlich zugänglicher Wert: Track.average_error
                                has_errors = False
                                for t in tracks:
                                    try:
                                        if (getattr(t, "average_error", 0.0) or 0.0) > 0.0:
                                            has_errors = True
                                            break
                                    except Exception:
                                        pass

                                # Timeout/Retry-Zähler
                                _wait_errors_then_clean._tries = getattr(_wait_errors_then_clean, "_tries", 0) + 1
                                if not has_errors and _wait_errors_then_clean._tries < 100:
                                    return 0.2  # weiter warten (max ~20s)

                                # Schwelle aus Scene.error_track (robust lesen)
                                try:
                                    thr = float(getattr(scene, "error_track", scene.get("error_track", 0.0)))
                                except Exception:
                                    thr = 0.0

                                # Pre-Clean Markeranzahl erfassen
                                scene["preclean_marker_count"] = _count_markers(clip)

                                if thr > 0.0:
                                    ov = _build_override(context)
                                    if ov:
                                        try:
                                            # nur „unsaubere Segmente“ entfernen, nicht ganze Tracks
                                            with context.temp_override(**ov):
                                                bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=0, error=thr, action='DELETE_SEGMENTS')
                                        except Exception as ex:
                                            self.report({'ERROR'}, f"Clean Tracks fehlgeschlagen: {ex}")

                                    # Watcher: Marker-Drop beobachten (0,2s)
                                    def _watch_marker_drop():
                                        cur = _count_markers(clip)
                                        scene["postclean_marker_count"] = cur
                                        if scene["preclean_marker_count"] >= 0 and cur < scene["preclean_marker_count"]:
                                            scene["marker_drop_detected"] = True
                                        # Beenden, sobald Phase 2 läuft
                                        return None if self._phase >= 2 else 0.2

                                    bpy.app.timers.register(_watch_marker_drop, first_interval=0.0)

                                # Zweiten Solve anstoßen (wie gefordert)
                                try:
                                    ov2 = _build_override(context)
                                    if ov2:
                                        with context.temp_override(**ov2):
                                            bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
                                    self._phase = 2
                                except Exception as ex2:
                                    self.report({'ERROR'}, f"Zweiter Solve-Start fehlgeschlagen: {ex2}")
                                    try:
                                        bpy.msgbus.clear_by_owner(owner)
                                    except Exception:
                                        pass
                                    return None

                                return None  # Timer erledigt

                            bpy.app.timers.register(_wait_errors_then_clean, first_interval=0.2)

                        # Wir bleiben subscribed; _finish pollt bis Solve 2 fertig
                        self._scheduled = False
                        return 0.2

                    # ---------------- PHASE 2 ----------------
                    else:
                        if avg is not None:
                            scene["solve_error_after_clean"] = float(avg)
                        scene["solve_status"] = "done_after_clean"
                        try:
                            bpy.msgbus.clear_by_owner(owner)
                        except Exception:
                            pass
                        self._scheduled = False
                        return None  # fertig

                else:
                    # noch nicht valide – in 0.2 s erneut prüfen
                    return 0.2

            bpy.app.timers.register(_finish, first_interval=0.0)

        # Subscriptions (reagieren auf Rekonstruktions-Updates)
        try:
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "is_valid"),
                owner=owner,
                args=(),
                notify=_notify,
            )
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "average_error"),
                owner=owner,
                args=(),
                notify=_notify,
            )
        except Exception as ex:
            self.report({'WARNING'}, f"Msgbus-Subscribe fehlgeschlagen: {ex}. Fallback: Polling in main.")
            scene["solve_watch_fallback"] = True

        # Ersten Solve starten – über den Helper (richtiger Kontext/Override)
        res = bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
        if res not in ({'FINISHED'}, {'RUNNING_MODAL'}):
            self.report({'ERROR'}, f"Camera Solve Start fehlgeschlagen: {res}")
            try:
                bpy.msgbus.clear_by_owner(owner)
            except Exception:
                pass
            return {'CANCELLED'}

        return {'FINISHED'}


# --- Register Boilerplate ---
_classes = (CLIP_OT_solve_camera_helper, CLIP_OT_watch_solve)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
