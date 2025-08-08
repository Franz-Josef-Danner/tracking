# Operator/main.py
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry  # bleibt importiert, falls dein UI das braucht

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

                # *** HIER Kontext setzen: nach Pipeline, vor Cleanup ***
                clip_area, clip_region, clip_space = _get_clip_editor_ctx(context)
                if not clip_space or not getattr(clip_space, "clip", None):
                    print("[Main] Kein CLIP_EDITOR-Kontext/Clip gefunden – skippe clean_error_tracks.")
                else:
                    # >>> CHANGE START: Cleanup nur wenn Pipeline nicht läuft
                    if scene.get("pipeline_status", "") == "running":
                        print("[Main] Pipeline läuft – skippe clean_error_tracks in diesem Tick.")
                    else:
                        with context.temp_override(area=clip_area, region=clip_region, space_data=clip_space):
                            bpy.context.view_layer.update()
                            context.scene.frame_set(context.scene.frame_current)
                            try:
                                print("[Main] Starte clean_error_tracks …")
                                ret = bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT', verbose=True)
                                print(f"[Main] clean_error_tracks result: {ret}")
                            except Exception as e:
                                print(f"[Main] clean_error_tracks Exception: {e}")
                    # >>> CHANGE END
                
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
                context.window_manager.event_timer_remove(self._timer)
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
                self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
                return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
