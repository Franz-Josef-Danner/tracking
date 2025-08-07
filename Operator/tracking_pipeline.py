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

    def execute(self, context):
        scene = context.scene

        # Statuswerte zurücksetzen
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""

        self._step = 0
        self._is_tracking = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)

        print("🚀 Starte Tracking-Pipeline...")
        scene["pipeline_status"] = "running"
        print(f"🧩 [DEBUG] pipeline_status gesetzt auf: {scene['pipeline_status']}")
        print(f"🧩 [DEBUG] Starte Modal Handler mit Kontext: {context.area.type if context.area else 'Unbekannt'}")

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Tracking-Pipeline manuell abgebrochen.")
            self.cancel(context)
            return {'CANCELLED'}
    
        if event.type == 'TIMER':
            return self.run_step(context)
    
        return {'PASS_THROUGH'}
    

    def run_step(self, context):
        scene = context.scene
        wm = context.window_manager
        clip = context.space_data.clip
        ts = clip.tracking.settings
        ts.default_margin = ts.default_search_size

        if self._step == 0:
            print("→ Marker Helper")
            bpy.ops.clip.marker_helper_main()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            print("→ Proxy deaktivieren")
            bpy.ops.clip.disable_proxy()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 2:
            print("→ Detect starten")
            bpy.ops.clip.detect()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 3:
            print("⏳ Warte auf Detect-Abschluss...")
        
            detect_status = scene.get("detect_status", "")
        
            if detect_status == "success":
                # ---- EINZIGE Anpassung laut deiner Vorgabe: Zyklus endet mit Proxy aktivieren ----
                print("→ Proxy aktivieren (Ende)")
                try:
                    bpy.ops.clip.enable_proxy()
                except Exception as e:
                    print(f"⚠️ Proxy-Aktivierung am Ende übersprungen/fehlgeschlagen: {e}")
                # -------------------------------------------------------------------------------
                print("✅ Detect fertig. Pipeline wird beendet.")
                scene["pipeline_status"] = "done"
                self.cancel(context)
                return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        self._is_tracking = False
        print("⛔ Pipeline abgebrochen und Timer entfernt.")

# (Optional) Registrierung, falls du die Klasse standalone testest
def register():
    bpy.utils.register_class(CLIP_OT_tracking_pipeline)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_pipeline)

if __name__ == "__main__":
    register()
