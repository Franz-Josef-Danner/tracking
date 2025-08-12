import bpy
from bpy.types import Operator
__all__ = ("CLIP_OT_solve_camera_helper", "CLIP_OT_watch_solve")


class CLIP_OT_watch_solve(bpy.types.Operator):
    bl_idname = "clip.watch_solve"
    bl_label = "Watch Camera Solve"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        scene = context.scene
        scene["solve_status"] = "pending"
        scene["solve_error"] = -1.0

        # --- Erweiterungs-Status (NEU, nicht invasiv) ---
        self._phase = 1                  # 1=nach erstem Solve, 2=nach Clean/zweitem Solve
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

                # --- Helper: Marker zählen (NEU) ---
                def _count_markers(c):
                    try:
                        tracks = c.tracking.objects.active.tracks
                    except Exception:
                        return 0
                    total = 0
                    for t in tracks:
                        try:
                            total += len(t.markers)
                        except Exception:
                            pass
                    return total
                # -----------------------------------

                # Rekonstruktion prüfen
                rec = None
                try:
                    rec = clip.tracking.objects.active.reconstruction if (clip and clip.tracking and clip.tracking.objects) else None
                except Exception:
                    rec = None
        
                if rec and getattr(rec, "is_valid", False):
                    avg = getattr(rec, "average_error", None)

                    # PHASE 1: erstes gültiges Solve -> Clean + zweites Solve vorbereiten
                    if self._phase == 1:
                        scene["solve_status"] = "done"
                        if avg is not None:
                            scene["solve_error"] = float(avg)

                        if not self._preclean_started:
                            self._preclean_started = True

                            # Warten bis Track-Fehlerwerte verfügbar sind (0,2 s Poll)
                            def _wait_errors_then_clean():
                                try:
                                    tracks = clip.tracking.objects.active.tracks
                                except Exception:
                                    return 0.2

                                # Track-average_error ist die stabilste öffentlich zugängliche Fehlergröße
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
                                    return 0.2  # weiter warten

                                # Schwelle aus Scene.error_track (robust lesen)
                                thr = 0.0
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

                                    # Watcher: Marker-Drop beobachten (0,2 s Poll)
                                    def _watch_marker_drop():
                                        cur = _count_markers(clip)
                                        scene["postclean_marker_count"] = cur
                                        if scene["preclean_marker_count"] >= 0 and cur < scene["preclean_marker_count"]:
                                            scene["marker_drop_detected"] = True
                                        # Beenden, sobald Phase 2 läuft
                                        return None if self._phase >= 2 else 0.2

                                    bpy.app.timers.register(_watch_marker_drop, first_interval=0.0)

                                # Zweiten Solve immer anstoßen (gemäß Anforderung)
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

                        # Wir bleiben weiter subscribed; _finish pollt bis Solve 2 fertig
                        self._scheduled = False
                        return 0.2

                    # PHASE 2: zweites Solve abgeschlossen
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

        # Subscriptions
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

        # Solve starten – nutzt deinen Helper (richtiger Kontext/Override)
        res = bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
        if res not in ({'FINISHED'}, {'RUNNING_MODAL'}):
            self.report({'ERROR'}, f"Camera Solve Start fehlgeschlagen: {res}")
            try:
                bpy.msgbus.clear_by_owner(owner)
            except Exception:
                pass
            return {'CANCELLED'}

        return {'FINISHED'}
