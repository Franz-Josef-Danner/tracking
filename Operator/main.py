# Operator/main.py
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry  # bleibt importiert, falls dein UI das braucht
from ..Helper.solve_camera_helper import solve_camera_helper  # Solver am Ende ausführen

def _get_clip_editor_ctx(context):
    """Finde CLIP_EDITOR area/region/space für temp_override."""
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0

    @classmethod
    def poll(cls, context):
        # Start nur aus dem CLIP_EDITOR mit geladenem Clip
        return (
            getattr(context, "space_data", None) and
            getattr(context.space_data, "type", "") == 'CLIP_EDITOR' and
            getattr(context.space_data, "clip", None) is not None
        )

    def execute(self, context):
        scene = context.scene

        # Reset aller relevanten Szene-Variablen
        scene["pipeline_status"] = ""
        scene["marker_min"] = 0
        scene["marker_max"] = 0
        scene["goto_frame"] = -1
        scene["solve_retry_count"] = 0  # <<< NEU: Retry-Zähler für Solve-Loop

        if hasattr(scene, "repeat_frame"):
            scene.repeat_frame.clear()

        # Clip prüfen
        clip = context.space_data.clip
        if clip is None or not clip.tracking:
            self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
            return {'CANCELLED'}

        # Einmalige Vorbereitung vor Zyklusstart
        bpy.ops.clip.tracker_settings('EXEC_DEFAULT')
        bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        # Pipeline starten
        bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

        # Modal-Loop starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._step = 0

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Tracking-Setup manuell abgebrochen.")
            context.window_manager.event_timer_remove(self._timer)

            # kompletter Reset
            scene = context.scene
            scene["pipeline_status"] = ""
            scene["marker_min"] = 0
            scene["marker_max"] = 0
            scene["goto_frame"] = -1
            if hasattr(scene, "repeat_frame"):
                scene.repeat_frame.clear()
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene
        repeat_collection = scene.repeat_frame

        # Warten bis die tracking_pipeline "done" meldet
        if self._step == 0:
            if scene.get("pipeline_status", "") == "done":
                self._step = 1
            return {'PASS_THROUGH'}

        # Nach Pipeline → Markercheck → ggf. Frame springen → DANN clean_error_tracks mit gültigem Kontext
        elif self._step == 1:
            clip = context.space_data.clip
            initial_basis = scene.get("marker_basis", 20)
            marker_basis  = scene.get("marker_basis", 20)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                scene["goto_frame"] = frame
                jump_to_frame(context)

                key = str(frame)
                entry = next((e for e in repeat_collection if e.frame == key), None)
                if entry:
                    entry.count += 1
                    marker_basis = min(int(marker_basis * 1.1), 100)
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)

                # Nächste Aktion: entweder optimieren oder erneut tracken
                if entry.count >= 10:
                    bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                else:
                    scene["marker_min"] = int(marker_basis * 0.9)
                    scene["marker_max"] = int(marker_basis * 1.1)
                    # neue Tracking-Runde starten
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

                self._step = 0  # zurück, bis wieder "done"
            else:
                # Kein Low-Marker-Frame mehr → letzter Cleanup und raus
                clip_area, clip_region, clip_space = _get_clip_editor_ctx(context)
                if clip_space and getattr(clip_space, "clip", None):
                    with context.temp_override(area=clip_area, region=clip_region, space_data=clip_space):
                        bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT', verbose=True)

                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            clip = context.space_data.clip
            marker_basis = scene.get("marker_basis", 20)
            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                self._step = 1
            else:
                # >>> erst Segmente löschen, dann leere Tracks entfernen
                bpy.ops.clip.clean_short_tracks('EXEC_DEFAULT', action='DELETE_SEGMENTS')
                bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=1, error=0.0, action='DELETE_TRACK')

                # >>> Kamera-Solve als letzter Schritt
                avg_err = None
                try:
                    res = solve_camera_helper(bpy.context)  # {'result': ..., 'valid': bool, 'average_error': float}
                    avg_err = res.get("average_error", None)
                except Exception as e:
                    print(f"[Solve] Exception: {e}")

                # >>> Threshold-Check & Re-Run-Logik (max. 3 Durchläufe)
                err_thresh = None
                try:
                    # Scene-Property via UI: layout.prop(scene, "error_track")
                    if hasattr(scene, "error_track"):
                        err_thresh = float(scene.error_track)
                except Exception:
                    err_thresh = None

                do_retry = False
                if avg_err is not None and err_thresh is not None:
                    do_retry = bool(avg_err > err_thresh)

                if do_retry and scene.get("solve_retry_count", 0) < 3:
                    # Marker-Adaptivität +10% – bevorzugt scene.marker_adapt, sonst marker_basis
                    try:
                        if hasattr(scene, "marker_adapt"):
                            scene.marker_adapt = float(scene.marker_adapt) * 1.1
                            basis = int(scene.marker_adapt)
                        else:
                            basis = int(scene.get("marker_basis", 20) * 1.1)
                            scene["marker_basis"] = basis
                        # Min/Max-Fenster aktualisieren
                        scene["marker_min"] = int(basis * 0.9)
                        scene["marker_max"] = int(basis * 1.1)
                    except Exception:
                        # Fallback ohne Crash
                        basis = int(scene.get("marker_basis", 20) * 1.1)
                        scene["marker_basis"] = basis
                        scene["marker_min"] = int(basis * 0.9)
                        scene["marker_max"] = int(basis * 1.1)

                    # Retry-Zähler erhöhen
                    scene["solve_retry_count"] = int(scene.get("solve_retry_count", 0)) + 1

                    # Pipeline neu anstoßen und in Step 0 zurück
                    try:
                        bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                    except Exception as e:
                        print(f"[Main] Retry start failed: {e}")

                    self._step = 0
                    return {'PASS_THROUGH'}
                else:
                    # Erfolg oder Max-Retries → sauber beenden
                    context.window_manager.event_timer_remove(self._timer)
                    self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
                    return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
