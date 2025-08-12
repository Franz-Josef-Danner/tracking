# main.py (überarbeitet – nur die geforderten Änderungen)
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry  # <- wichtig!
from ..Helper.solve_camera_helper import CLIP_OT_solve_watch_clean

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

        # Error-Limit Snapshot (unverändert)
        try:
            scene["error_limit_run"] = float(getattr(scene, "error_track"))
        except Exception:
            scene["error_limit_run"] = float(scene.get("error_track", 0.0))

        if hasattr(scene, "repeat_frame"):
            scene.repeat_frame.clear()

        # Clip-Zustand prüfen (unverändert)
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
        if clip is None or not getattr(clip, "tracking", None):
            self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Vorbereitung...")

        # Vorbereitungen (unverändert)
        bpy.ops.clip.tracker_settings('EXEC_DEFAULT')
        bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        # ❌ Entfernt: KEINE Playhead-Setzung vor Pipeline-Start mehr

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
                    scene["marker_basis"] = marker_basis
                    print(f"🔺 Selber Frame erneut – erhöhe marker_basis auf {marker_basis}")
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)
                    scene["marker_basis"] = marker_basis
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

                self._step = 0
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
                return {'PASS_THROUGH'}

            # ✨ Neues Ende: Solve starten und beenden
            print("🏁 Keine Low-Marker-Frames mehr gefunden. Starte Kamera-Solve und beende.")
            # CLIP_EDITOR-Kontext sichern
            area_ce = region_ce = space_ce = None
            for a in context.screen.areas:
                if a.type == 'CLIP_EDITOR':
                    for r in a.regions:
                        if r.type == 'WINDOW':
                            area_ce = a
                            region_ce = r
                            space_ce = a.spaces.active
            if area_ce and region_ce and space_ce:
                with context.temp_override(area=area_ce, region=region_ce, space_data=space_ce):
                    # Verwende deinen Helper, da er bereits im Projekt genutzt wird
                    ..Helper
                    bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')
            else:
                # Fallback – versucht Solve im aktuellen Kontext
                bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')

            # Timer entfernen und sauber beenden
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            return {'FINISHED'}

        # ❌ Step 3 entfällt komplett (Error-Validator & Restart entfernt)

        return {'RUNNING_MODAL'}
