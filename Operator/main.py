# main.py (überarbeitet)
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry  # <- wichtig!

class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0

    def execute(self, context):
        scene = context.scene
        scene["solve_status"] = ""
        scene["solve_error"] = -1.0
        scene["solve_watch_fallback"] = False
        scene["pipeline_status"] = ""
        scene["marker_min"] = 0
        scene["marker_max"] = 0
        scene["goto_frame"] = -1

        # --- NEU: Error-Limit Snapshot einmalig zum Run-Beginn sichern ---
        try:
            scene["error_limit_run"] = float(getattr(scene, "error_track"))
        except Exception:
            scene["error_limit_run"] = float(scene.get("error_track", 0.0))
        # ------------------------------------------------------------------

        if hasattr(scene, "repeat_frame"):
            scene.repeat_frame.clear()

        # Optional: Clip-Zustand prüfen
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
        if clip is None or not getattr(clip, "tracking", None):
            self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Vorbereitung...")

        # 🔧 EINMALIGE Vorbereitung vor Zyklusstart
        bpy.ops.clip.tracker_settings('EXEC_DEFAULT')
        bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        # --- NEU: Vor Detect/Tracking zuerst Low-Marker-Frame suchen & Playhead setzen ---
        try:
            marker_basis = scene.get("marker_basis", 25)
        except Exception:
            marker_basis = 25
        frame = find_low_marker_frame(clip, marker_basis=marker_basis)
        if frame is not None:
            scene["goto_frame"] = frame
            print(f"🎯 Zyklus-Start: Springe auf Low-Marker-Frame {frame} (Basis={marker_basis})")
            jump_to_frame(context)
        # ---------------------------------------------------------------------------------

        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
        print("⏳ Warte auf Abschluss der Pipeline...")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._step = 0

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Tracking-Setup manuell abgebrochen.")
            context.window_manager.event_timer_remove(self._timer)

            # 🔁 Kompletter Reset der Szenevariablen
            scene = context.scene
            scene["pipeline_status"] = ""
            scene["marker_min"] = 0
            scene["marker_max"] = 0
            scene["goto_frame"] = -1
            if hasattr(scene, "repeat_frame"):
                scene.repeat_frame.clear()

            print("❌ Abbruch durch Benutzer – Setup zurückgesetzt.")
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene
        repeat_collection = scene.repeat_frame

        if self._step == 0:
            if scene.get("pipeline_status", "") == "done":
                print("🧪 Starte Markerprüfung…")
                self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None)
            if clip is None or not getattr(clip, "tracking", None):
                self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
                return {'CANCELLED'}
            initial_basis = scene.get("marker_basis", 25)
            marker_basis = scene.get("marker_basis", 25)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                print(f"🟡 Zu wenige Marker im Frame {frame}")
                scene["goto_frame"] = frame
                jump_to_frame(context)

                key = str(frame)
                entry = next((e for e in repeat_collection if e.frame == key), None)

                if entry:
                    entry.count += 1
                    marker_basis = min(int(marker_basis * 1.1), 100)
                    scene["marker_basis"] = marker_basis  # <-- persistieren
                    print(f"🔺 Selber Frame erneut – erhöhe marker_basis auf {marker_basis}")
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)
                    scene["marker_basis"] = marker_basis  # <-- persistieren
                    print(f"🔻 Neuer Frame – senke marker_basis auf {marker_basis}")

                print(f"🔁 Frame {frame} wurde bereits {entry.count}x erkannt.")

                if entry.count >= 10:
                    print(f"🚨 Optimiere Tracking für Frame {frame}")
                    bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                else:
                    scene["marker_min"] = int(marker_basis * 0.9)
                    scene["marker_max"] = int(marker_basis * 1.1)
                    print(f"🔄 Neuer Tracking-Zyklus mit Marker-Zielwerten {scene['marker_min']}–{scene['marker_max']}")
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

                self._step = 0  # Wiederhole Zyklus
            else:
                print("✅ Alle Frames haben ausreichend Marker. Cleanup wird ausgeführt.")
                bpy.ops.clip.clean_error_tracks('INVOKE_DEFAULT')
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None)
            if clip is None or not getattr(clip, "tracking", None):
                self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
                return {'CANCELLED'}
            marker_basis = scene.get("marker_basis", 20)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                print(f"🔁 Neuer Low-Marker-Frame gefunden: {frame} → Starte neuen Zyklus.")
                self._step = 1
            else:
                print("🏁 Keine Low-Marker-Frames mehr gefunden. Beende Prozess.")
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')

                scene = context.scene
                scene["solve_status"] = "pending"
                time.sleep(1)
                bpy.ops.clip.watch_solve('INVOKE_DEFAULT')
                self._step = 3
                return {'PASS_THROUGH'}

        elif self._step == 3:
            scene = context.scene

            # Clip & Reconstruction robust ermitteln (kontexttolerant)
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None)
            rec = None
            try:
                if clip and getattr(clip, "tracking", None) and clip.tracking.objects:
                    rec = clip.tracking.objects.active.reconstruction
            except Exception:
                rec = None

            # Primärer Abschlussweg: aktives Polling statt Event-Abhängigkeit
            if rec and getattr(rec, "is_valid", False):
                err_val = float(getattr(rec, "average_error", -1.0))

                # Limit bevorzugt aus Run-Snapshot lesen; Fallback auf aktuelle UI/IDProp
                limit_val = float(scene.get("error_limit_run",
                                            getattr(scene, "error_track", scene.get("error_track", 0.0))))

                path = "Poll" if scene.get("solve_watch_fallback", False) else "Msgbus"
                print(f"✅ [{path}] Camera Solve fertig. Average Error: {err_val:.3f} px (Limit: {limit_val:.3f} px)")

                # Entscheidung OK/FAILED
                if err_val > limit_val:
                    print(f"[Solve-Check] FAILED (Error={err_val:.3f} px > Limit={limit_val:.3f} px)")
                    self.report({'ERROR'}, f"Solve-Error {err_val:.3f} px > Limit {limit_val:.3f} px → FAILED")

                    # --- marker_basis erhöhen, Zielbereich setzen, Pipeline neu starten, Modal fortsetzen ---
                    marker_basis = scene.get("marker_basis", 20)
                    marker_basis = min(int(marker_basis * 1.1), 100)
                    scene["marker_basis"] = marker_basis
                    scene["marker_min"] = int(marker_basis * 0.9)
                    scene["marker_max"] = int(marker_basis * 1.1)
                    print(f"🔺 Erhöhe marker_basis auf {marker_basis} und starte Zyklus neu "
                          f"({scene['marker_min']}–{scene['marker_max']})")
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                    self._step = 0
                    return {'PASS_THROUGH'}

                print(f"[Solve-Check] OK (Error={err_val:.3f} px ≤ Limit={limit_val:.3f} px)")
                self.report({'INFO'}, f"Solve-Error {err_val:.3f} px innerhalb des Limits.")
                try:
                    context.window_manager.event_timer_remove(self._timer)
                except Exception:
                    pass
                scene["solve_watch_fallback"] = False
                scene["solve_status"] = ""
                return {'FINISHED'}

            # Sekundär: Wenn der Watcher doch ein Flag setzt, eine Schleife später erneut pollen.
            if scene.get("solve_status", "") == "done":
                return {'PASS_THROUGH'}

            # Solve läuft oder Rekonstruktion noch nicht gültig → weiter pollen
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
