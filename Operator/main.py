import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame

class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        if clip is None or not clip.tracking:
            self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
        print("⏳ Warte auf Abschluss der Pipeline...")

        # Property-Absicherung
        if not isinstance(scene.get("repeat_frame"), dict):
            print("⚠️ [DEBUG] Ungültiger repeat_frame-Wert erkannt – wird zurückgesetzt.")
            scene["repeat_frame"] = {}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._step = 0

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene
        repeat_dict = scene.get("repeat_frame", {})

        if self._step == 0:
            if scene.get("pipeline_status", "") == "done":
                print("🧪 Starte Markerprüfung…")
                self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            clip = context.space_data.clip
            marker_basis = scene.get("marker_basis", 20)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                print(f"🟡 Zu wenige Marker im Frame {frame}")
                scene["goto_frame"] = frame
                jump_to_frame(context)

                key = str(frame)
                if key in repeat_dict:
                    repeat_dict[key] += 1
                else:
                    repeat_dict[key] = 1

                print(f"🔁 Frame {frame} wurde bereits {repeat_dict[key]}x erkannt.")

                if repeat_dict[key] >= 10:
                    print(f"🚨 Optimiere Tracking für Frame {frame}")
                    bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                else:
                    scene["marker_min"] = max(int(marker_basis * 0.9), 10)
                    scene["marker_max"] = min(int(marker_basis * 1.1), 100)
                    print(f"🔄 Neuer Tracking-Zyklus mit Marker-Zielwerten {scene['marker_min']}–{scene['marker_max']}")
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

                scene["repeat_frame"] = repeat_dict
                self._step = 0
            else:
                print("✅ Alle Frames haben ausreichend Marker. Cleanup wird ausgeführt.")
                bpy.ops.clip.clean_error_tracks('INVOKE_DEFAULT')
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            context.window_manager.event_timer_remove(self._timer)
            self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
            return {'FINISHED'}

        return {'RUNNING_MODAL'}
