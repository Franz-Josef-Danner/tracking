import bpy, time
from ..Helper.ram_helper import RamGuard

class CLIP_OT_tracking_pipeline(bpy.types.Operator):
    """Tracking-Pipeline: Detect, Track, Cleanup"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _is_tracking = False
    _ram_guard = None

    def execute(self, context):
        # RamGuard initialisieren (Self-Bootstrap kümmert sich um psutil)
        self._ram_guard = RamGuard(threshold_up=90.0, threshold_down=80.0, cooldown=5.0)

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
            # RAM prüfen, bevor wir Step-Logik machen
            if self._ram_guard:
                event_name, pct = self._ram_guard.poll()
                if event_name == 'enter_hot':
                    print(f"🔥 RAM {pct:.1f}% – Proxy-Flush wird ausgeführt")
                    try:
                        bpy.ops.clip.enable_proxy()
                        bpy.ops.clip.reload()
                        bpy.ops.clip.disable_proxy()
                        bpy.ops.clip.reload()
                    except Exception as e:
                        print(f"⚠️ Proxy-Flush fehlgeschlagen: {e}")

            return self.run_step(context)

        return {'PASS_THROUGH'}

    def run_step(self, context):
        scene = context.scene
        wm = context.window_manager
        clip = context.space_data.clip
        ts = clip.tracking.settings
        ts.default_margin = ts.default_search_size

        if self._step == 0:
            print("→ Proxy aktivieren (Init)")
            try:
                bpy.ops.clip.enable_proxy()
            except Exception as e:
                print(f"⚠️ Proxy-Aktivierung (Init) übersprungen/fehlgeschlagen: {e}")
            print("→ Proxy deaktivieren (Init)")
            try:
                bpy.ops.clip.disable_proxy()
            except Exception as e:
                print(f"⚠️ Proxy-Deaktivierung (Init) übersprungen/fehlgeschlagen: {e}")

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
                self._step += 1
                scene["detect_status"] = ""
                return {'PASS_THROUGH'}
            elif detect_status == "failed":
                self.report({'ERROR'}, "❌ Detect fehlgeschlagen – Pipeline wird abgebrochen.")
                self.cancel(context)
                return {'CANCELLED'}
            return {'PASS_THROUGH'}

        elif self._step == 4:
            print("→ Proxy-Parameter reset (kein Aktivieren an dieser Stelle)")
            ts = context.space_data.clip.tracking.settings
            ts.default_margin = ts.default_search_size
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 5:
            print("→ Starte bidirektionales Tracking")
            bpy.ops.clip.bidirectional_track()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 6:
            if scene.get("bidirectional_status", "") == "done":
                print("✅ Bidirectional Tracking abgeschlossen.")
                scene["bidirectional_status"] = ""
                self._is_tracking = False

            if not self._is_tracking:
                print("⏳ Warte auf Abschluss der Pipeline...")
                scene["pipeline_status"] = "done"
                print(f"🧩 [DEBUG] pipeline_status gesetzt auf: {scene['pipeline_status']}")
                print("→ Proxy aktivieren (Ende)")
                try:
                    bpy.ops.clip.enable_proxy()
                except Exception as e:
                    print(f"⚠️ Proxy-Aktivierung am Ende übersprungen/fehlgeschlagen: {e}")
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        scene = context.scene
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""
        scene["goto_frame"] = -1
        if "repeat_frame" in scene:
            scene["repeat_frame"].clear()
        print("❌ Tracking Pipeline abgebrochen. Status zurückgesetzt.")
