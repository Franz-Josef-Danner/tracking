import bpy
import time

class CLIP_OT_tracking_pipeline(bpy.types.Operator):
    """Tracking-Pipeline: Detect, Track, Cleanup"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _is_tracking = False

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.run_step(context)
        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._step = 0
        self._is_tracking = True
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)

        print("🚀 Starte Tracking-Pipeline...")
        context.scene["pipeline_status"] = "running"
        print(f"🧩 [DEBUG] pipeline_status gesetzt auf: {context.scene['pipeline_status']}")
        print(f"🧩 [DEBUG] Starte Modal Handler mit Kontext: {context.area.type if context.area else 'Unbekannt'}")

        return {'RUNNING_MODAL'}

    def run_step(self, context):
        scene = context.scene
        wm = context.window_manager

        # Rückmeldung vom Bidirectional Tracking
        if scene.get("bidirectional_status", "") == "done":
            self._is_tracking = False
            scene["bidirectional_status"] = ""  # Reset
            print("✅ Bidirectional Tracking abgeschlossen.")

        if self._step == 0:
            print("→ Marker Helper")
            bpy.ops.clip.marker_helper_main()
            self._step += 1

        elif self._step == 1:
            print("→ Proxy deaktivieren")
            bpy.ops.clip.disable_proxy()
            self._step += 1

        elif self._step == 2:
            print("→ Detect starten")
            bpy.ops.clip.detect()
            self._step += 1

        elif self._step == 3:
            print("⏳ Warte auf Detect-Abschluss...")
            if scene.get("detect_status", "") == "success":
                self._step += 1
                scene["detect_status"] = ""
                print("✅ Detect abgeschlossen.")

        elif self._step == 4:
            print("→ Proxy aktivieren")
            bpy.ops.clip.enable_proxy()
            self._step += 1

        elif self._step == 5:
            print("→ Starte bidirektionales Tracking")
            bpy.ops.clip.bidirectional_track()
            self._step += 1  # Weiter zu Schritt 6 (Warten auf Tracking-Ende)

        elif self._step == 6:
            if scene.get("bidirectional_status", "") == "done":
                print("✅ Bidirectional Tracking abgeschlossen.")
                scene["bidirectional_status"] = ""
                self._is_tracking = False
        
            if not self._is_tracking:
                print("⏳ Warte auf Abschluss der Pipeline...")
                scene["pipeline_status"] = "done"
                print(f"🧩 [DEBUG] pipeline_status gesetzt auf: {scene['pipeline_status']}")
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

