import bpy
import time

class TrackingController:
    def __init__(self, context):
        self.context = context
        self.scene = context.scene
        self.initial_frame = context.scene.frame_current
        self.step = 0

    def run(self):
        print(f"[Tracking] Schritt: {self.step}")

        # Sicherstelle, dass wir im Clip-Editor sind
        clip_area = next((area for area in bpy.context.window.screen.areas if area.type == 'CLIP_EDITOR'), None)
        if not clip_area:
            print("⚠ Kein Clip-Editor gefunden!")
            return None

        with bpy.context.temp_override(area=clip_area):
            if self.step == 0:
                print("→ Starte Vorwärts-Tracking...")
                invoke_clip_operator_safely("track_markers", backwards=False, sequence=True)
                self.step = 1

            elif self.step == 1:
                print("→ Warte auf Abschluss des Vorwärts-Trackings...")
                if self.is_tracking_done_robust():
                    print("✓ Vorwärts-Tracking abgeschlossen.")
                    self.scene.frame_current = self.initial_frame
                    print(f"← Frame zurückgesetzt auf {self.initial_frame}")
                    self.step = 2

            elif self.step == 2:
                print("→ Starte Rückwärts-Tracking...")
                invoke_clip_operator_safely("track_markers", backwards=True, sequence=True)
                self.step = 3

            elif self.step == 3:
                print("→ Warte auf Abschluss des Rückwärts-Trackings...")
                if self.is_tracking_done_robust():
                    print("✓ Rückwärts-Tracking abgeschlossen.")
                    self.step = 4

            elif self.step == 4:
                print("→ Starte Bereinigung kurzer Tracks...")
                self.cleanup_short_tracks()
                print("✓ Tracking und Cleanup abgeschlossen.")
                return None

        return 0.5  # Nächste Ausführung in 0.5 Sekunden

    def is_tracking_done_robust(self):
        # Hier kannst du eine robustere Logik einbauen z.B. Markeranzahl oder Playhead-Stop
        return True

    def cleanup_short_tracks(self):
        # Dummyfunktion zur Bereinigung, implementieren je nach Bedarf
        pass

def invoke_clip_operator_safely(operator_name, **kwargs):
    if hasattr(bpy.ops.clip, operator_name):
        op = getattr(bpy.ops.clip, operator_name)
        if op.poll():
            print(f"→ bpy.ops.clip.{operator_name} ausführen")
            op('INVOKE_DEFAULT', **kwargs)
        else:
            print(f"⚠ bpy.ops.clip.{operator_name}.poll() fehlgeschlagen")
    else:
        print(f"⚠ Operator bpy.ops.clip.{operator_name} existiert nicht")

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Tracks markers forward and backward with pause monitoring"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        controller = TrackingController(context)
        bpy.app.timers.register(controller.run, first_interval=0.1)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)

if __name__ == "__main__":
    register()
