# main.py (überarbeitet)
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry
from ..Helper.solve_camera_helper import CLIP_OT_solve_camera_helper

def _select_all_markers(clip):
    """Selektiert alle Tracks und – falls verfügbar – alle Marker des Clips."""
    if clip is None:
        return
    tracking = clip.tracking
    for t in tracking.tracks:
        t.select = True  # Track-Selektion
        # Marker-Selektion (falls API-Feld vorhanden)
        for m in getattr(t, "markers", []):
            try:
                m.select = True
            except Exception:
                pass

class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0

    def _solve_watch_register(self, context):
        """Registriert einen RNA-Listener auf den Solve-Status."""
        import bpy
        self._solve_token = object()
        self._solve_done = False
        self._solve_failed = False
        self._solve_started_at = time.time()
    
        # Callback: prüft, ob Rekonstruktion gültig ist
        def _on_change():
            try:
                space = context.space_data
                clip = getattr(space, "clip", None)
                if not clip:
                    return
                obj = clip.tracking.objects.active
                if obj and obj.reconstruction and obj.reconstruction.is_valid:
                    self._solve_done = True
            except Exception:
                # Im Zweifel als Fehler markieren
                self._solve_failed = True
    
        self._on_solve_change = _on_change  # Referenz halten
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.MovieTrackingReconstruction, "is_valid"),
            owner=self._solve_token,
            args=(),
            notify=_on_change,
            options={'PERSISTENT'},
        )

    def _solve_watch_unregister(self):
        """Entfernt den RNA-Listener, falls vorhanden."""
        import bpy
        try:
            if getattr(self, "_solve_token", None):
                bpy.msgbus.clear_by_owner(self._solve_token)
        except Exception:
            pass
        self._solve_token = None
    
    
        def execute(self, context):
            scene = context.scene
        
            # Reset aller relevanten Szene-Variablen
            scene["pipeline_status"] = ""
            scene["marker_min"] = 0
            scene["marker_max"] = 0
            scene["goto_frame"] = -1
        
            if hasattr(scene, "repeat_frame"):
                scene.repeat_frame.clear()
        
            # Optional: Clip-Zustand prüfen
            clip = context.space_data.clip
            if clip is None or not clip.tracking:
                self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
                return {'CANCELLED'}
        
            print("🚀 Starte Tracking-Vorbereitung...")
        
            # 🔧 EINMALIGE Vorbereitung vor Zyklusstart
            bpy.ops.clip.tracker_settings('EXEC_DEFAULT')
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')
        
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
            clip = context.space_data.clip
            initial_basis = scene.get("marker_basis")
            marker_basis = scene.get("marker_basis")


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
                    print(f"🔺 Selber Frame erneut – erhöhe marker_basis auf {marker_basis}")
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)
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
                clip = context.space_data.clip
                _select_all_markers(clip)
                bpy.ops.clip.clean_error_tracks('INVOKE_DEFAULT')
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            clip = context.space_data.clip
            marker_basis = scene.get("marker_basis", 20)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                print(f"🔁 Neuer Low-Marker-Frame gefunden: {frame} → Starte neuen Zyklus.")
                self._step = 1
            else:
                print("🏁 Keine Low-Marker-Frames mehr gefunden. Beende Prozess.")
                context.window_manager.event_timer_remove(self._timer)
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
                
                # NEU: finaler Kamera-Solve (invoke)
                try:
                    print("🎯 Final: Starte Kamera-Solver…")
                    self._solve_watch_register(context)
                    print("🎯 Final: Starte Kamera-Solver…")
                    bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
                    self._step = 3
                    return {'PASS_THROUGH'}
                except Exception as e:
                    self.report({'WARNING'}, f"Kamera-Solver konnte nicht gestartet werden: {e}")

            elif self._step == 3:
                # Fertig?
                if getattr(self, "_solve_done", False):
                    print("✅ Kamera-Solve abgeschlossen.")
                    self._solve_watch_unregister()
                    try:
                        context.window_manager.event_timer_remove(self._timer)
                    except Exception:
                        pass
                    self.report({'INFO'}, "Tracking + Solve abgeschlossen.")
                    return {'FINISHED'}
            
                # Fehlersignal vom Callback?
                if getattr(self, "_solve_failed", False):
                    print("❌ Kamera-Solve meldet Fehler.")
                    self._solve_watch_unregister()
                    self.report({'WARNING'}, "Kamera-Solve fehlgeschlagen.")
                    return {'CANCELLED'}
            
                # Timeout als Fail-Safe (z. B. 120s)
                if time.time() - getattr(self, "_solve_started_at", time.time()) > 120:
                    print("⏱️ Timeout: Keine Bestätigung vom Kamera-Solve.")
                    self._solve_watch_unregister()
                    self.report({'WARNING'}, "Kamera-Solve Timeout.")
                    return {'CANCELLED'}
            
                return {'PASS_THROUGH'}


                self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
                return {'FINISHED'}


            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
