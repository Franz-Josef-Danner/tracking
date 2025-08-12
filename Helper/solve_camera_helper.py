import bpy
from bpy.types import Operator

class CLIP_OT_watch_solve(bpy.types.Operator):
    bl_idname = "clip.watch_solve"
    bl_label = "Watch Camera Solve (Clean & Re-Solve)"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        scene = context.scene
        scene["solve_status"] = "pending"
        scene["solve_error"] = -1.0
        scene["solve_error_after_clean"] = -1.0

        # Guard-/State
        self._phase = 1                  # 1 = erster Solve, 2 = nach Cleanup
        self._scheduled = False
        self._owner = object()           # für msgbus clear

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
                    avg = float(getattr(rec, "average_error", 0.0))

                    # PHASE 1: Solve fertig -> Clean nach Error-Threshold + Re-Solve
                    if self._phase == 1:
                        scene["solve_status"] = "done"
                        scene["solve_error"] = avg

                        thr = float(getattr(scene, "error_track", 0.0))
                        if thr <= 0.0:
                            # Kein Threshold gesetzt -> keine zweite Runde
                            try:
                                bpy.msgbus.clear_by_owner(self._owner)
                            except Exception:
                                pass
                            self._scheduled = False
                            return None

                        # Cleanup + sofort erneut lösen
                        ovr = _build_override(context)
                        if not ovr:
                            self.report({'ERROR'}, "CLIP_EDITOR-Kontext fehlt für Cleanup.")
                            try:
                                bpy.msgbus.clear_by_owner(self._owner)
                            except Exception:
                                pass
                            self._scheduled = False
                            return None

                        try:
                            with bpy.context.temp_override(**ovr):
                                # nur Fehlerbereinigung, keine Frame-Limit-Bereinigung
                                bpy.ops.clip.clean_tracks(frames=0, error=thr, action='DELETE_SEGMENTS')
                                # optionaler UI-Refresh
                                try:
                                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                                except Exception:
                                    pass
                                # zweiter Solve
                                bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
                        except Exception as ex:
                            self.report({'ERROR'}, f"Cleanup/Re-Solve fehlgeschlagen: {ex}")
                            try:
                                bpy.msgbus.clear_by_owner(self._owner)
                            except Exception:
                                pass
                            self._scheduled = False
                            return None

                        # in Phase 2 wechseln und Polling fortsetzen
                        self._phase = 2
                        self._scheduled = False
                        return 0.2

                    # PHASE 2: zweiter Solve ist fertig -> Finalisieren
                    else:
                        scene["solve_status"] = "done_after_clean"
                        scene["solve_error_after_clean"] = avg
                        try:
                            bpy.msgbus.clear_by_owner(self._owner)
                        except Exception:
                            pass
                        self._scheduled = False
                        return None

                # (noch) nicht valide -> weiter pollen
                self._scheduled = False
                return 0.2

            # Timer starten (Polling-Fallback ist robust gegenüber Msgbus-Besonderheiten)
            bpy.app.timers.register(_finish, first_interval=0.0)

        # Msgbus-Subscriptions (Valid-Flag & Error-Änderung triggern Notify)
        try:
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "is_valid"),
                owner=self._owner,
                args=(),
                notify=_notify,
            )
            bpy.msgbus.subscribe_rna(
                key=(bpy.types.MovieTrackingReconstruction, "average_error"),
                owner=self._owner,
                args=(),
                notify=_notify,
            )
        except Exception as ex:
            self.report({'WARNING'}, f"Msgbus-Subscribe fehlgeschlagen: {ex}. Fallback: reines Polling.")
            # reines Polling anwerfen
            bpy.app.timers.register(lambda: (_notify(), None)[1], first_interval=0.0)

        # Ersten Solve im korrekten UI-Kontext starten
        res = bpy.ops.clip.solve_camera_helper('INVOKE_DEFAULT')
        if res not in ({'FINISHED'}, {'RUNNING_MODAL'}):
            self.report({'ERROR'}, f"Camera Solve Start fehlgeschlagen: {res}")
            try:
                bpy.msgbus.clear_by_owner(self._owner)
            except Exception:
                pass
            return {'CANCELLED'}

        return {'FINISHED'}
