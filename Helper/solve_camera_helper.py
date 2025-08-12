class CLIP_OT_watch_solve(bpy.types.Operator):
    bl_idname = "clip.watch_solve"
    bl_label = "Watch Camera Solve"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        scene = context.scene
        scene["solve_status"] = "pending"
        scene["solve_error"] = -1.0

        # --- EXTENSION: State für Zweiphasen-Flow ---
        self._phase = "solve1"            # solve1 -> cleanup -> solve2 -> done
        self._second_solve_started = False
        self._wait_errors_tries = 0
        scene["preclean_marker_count"] = -1
        scene["postclean_marker_count"] = -1
        scene["marker_drop_detected"] = False
        # --- EXTENSION ENDE ---

        owner = object()
        self._owner = owner
        self._scheduled = False

        def _notify(*_args):
            if self._scheduled:
                return
            self._scheduled = True

            def _finish():
                # Clip robust holen (unverändert)
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

                # Rekonstruktion prüfen (unverändert)
                rec = None
                try:
                    rec = clip.tracking.objects.active.reconstruction if (clip and clip.tracking and clip.tracking.objects) else None
                except Exception:
                    rec = None

                # --- EXTENSION: kleine Helfer ---
                def _count_markers(_clip):
                    try:
                        tracks = _clip.tracking.objects.active.tracks
                    except Exception:
                        return 0
                    total = 0
                    for t in tracks:
                        total += len(t.markers)
                    return total

                def _get_error_threshold():
                    thr = getattr(scene, "error_track", None)
                    if thr is None:
                        thr = scene.get("error_track", 1.0)  # Fallback
                    try:
                        return float(thr)
                    except Exception:
                        return 1.0

                def _override():
                    return _build_override(context)
                # --- EXTENSION ENDE ---

                if rec and getattr(rec, "is_valid", False):
                    avg = getattr(rec, "average_error", None)

                    # --- EXTENSION: Phasensteuerung ---
                    if self._phase == "solve1":
                        # Phase 1 abgeschlossen -> vor Cleanup Errors abwarten
                        scene["solve_status"] = "done"  # beibehaltener Status
                        if avg is not None:
                            scene["solve_error"] = float(avg)

                        def _wait_errors_then_clean():
                            # Warte, bis Track-Errors sinnvoll befüllt sind
                            self._wait_errors_tries += 1
                            try:
                                tracks = clip.tracking.objects.active.tracks
                            except Exception:
                                return 0.2

                            has_errors = any((getattr(t, "average_error", 0.0) or 0.0) > 0.0 for t in tracks)
                            # Timeout, falls nichts kommt (z.B. exotischer Clip-Zustand)
                            if not has_errors and self._wait_errors_tries < 100:
                                return 0.2

                            # Cleanup fahren
                            scene["preclean_marker_count"] = _count_markers(clip)
                            thr = _get_error_threshold()
                            ov = _override()
                            if not ov:
                                self.report({'ERROR'}, "Clip-Override fehlt für Clean Tracks.")
                                return None
                            try:
                                with context.temp_override(**ov):
                                    # Löscht Marker-Segmente mit zu hohem Fehler (offizieller Operator)
                                    bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=0, error=thr, action='DELETE_SEGMENTS')
                            except Exception as ex:
                                self.report({'ERROR'}, f"Clean Tracks fehlgeschlagen: {ex}")
                                return None

                            # Nach Cleanup: Marker-Reduktion beobachten; wenn geringer -> zweites Solve starten
                            def _monitor_drop_and_resolve():
                                cur = _count_markers(clip)
                                scene["postclean_marker_count"] = cur
                                if (cur < scene["preclean_marker_count"]) and not self._second_solve_started:
                                    scene["marker_drop_detected"] = True
                                    self._second_solve_started = True
                                    try:
                                        with context.temp_override(**ov):
                                            res2 = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
                                        if res2 not in ({'FINISHED'}, {'RUNNING_MODAL'}):
                                            self.report({'ERROR'}, f"Zweiter Solve-Start fehlgeschlagen: {res2}")
                                            return None
                                        self._phase = "solve2"
                                    except Exception as ex2:
                                        self.report({'ERROR'}, f"Zweiter Solve fehlgeschlagen: {ex2}")
                                        return None

                                # Weiter poll’en, bis solve2 final durch ist
                                if self._phase == "solve2_done":
                                    return None
                                return 0.2

                            bpy.app.timers.register(_monitor_drop_and_resolve, first_interval=0.0)
                            return None  # _wait_errors_then_clean beendet

                        bpy.app.timers.register(_wait_errors_then_clean, first_interval=0.2)
                        # WICHTIG: Msgbus NICHT räumen – wir brauchen ihn für solve2
                        self._scheduled = False
                        return 0.2

                    elif self._phase == "solve2":
                        # Zweites Solve jetzt gültig -> final abschließen
                        scene["solve_status"] = "done"
                        if avg is not None:
                            scene["solve_error"] = float(avg)
                        self._phase = "solve2_done"
                        try:
                            bpy.msgbus.clear_by_owner(owner)
                        except Exception:
                            pass
                        self._scheduled = False
                        return None
                    # --- EXTENSION ENDE ---

                    # (Fallback: sollte eigentlich nicht erreicht werden)
                    try:
                        bpy.msgbus.clear_by_owner(owner)
                    except Exception:
                        pass
                    self._scheduled = False
                    return None
                else:
                    # noch nicht valide – in 0.2 s erneut prüfen
                    return 0.2

            bpy.app.timers.register(_finish, first_interval=0.0)

        # Subscriptions (unverändert)
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

        # Solve starten (unverändert)
        res = bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
        if res not in ({'FINISHED'}, {'RUNNING_MODAL'}):
            self.report({'ERROR'}, f"Camera Solve Start fehlgeschlagen: {res}")
            try:
                bpy.msgbus.clear_by_owner(owner)
            except Exception:
                pass
            return {'CANCELLED'}

        return {'FINISHED'}
