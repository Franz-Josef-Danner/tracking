import bpy
from bpy.types import Operator

# Globale Variablen für Timer-Zustand
previous_frame = -1
previous_track_count = -1
no_change_counter = 0


def wait_for_tracking_stability():
    """Timer-Funktion prüft, ob sich Frame & Track-Zahl nicht mehr ändern"""
    global previous_frame, previous_track_count, no_change_counter

    context = bpy.context
    scene = context.scene
    clip = context.space_data.clip

    if not clip:
        print("❌ Kein aktiver Clip gefunden.")
        return None

    current_frame = scene.frame_current
    current_track_count = len(clip.tracking.tracks)

    if current_frame == previous_frame and current_track_count == previous_track_count:
        no_change_counter += 1
    else:
        no_change_counter = 0

    previous_frame = current_frame
    previous_track_count = current_track_count

    print(f"[⏱️] Warte auf Stabilität… Frame: {current_frame}, Tracks: {current_track_count}, Still: {no_change_counter}/2")

    if no_change_counter >= 2:
        print("✅ Stabil – führe clean_short_tracks aus.")
        bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
        return None  # Timer stoppen

    return 1.0  # Wiederhole nach 1 Sekunde


class CLIP_OT_tracking_pipeline(Operator):
    """Führt die vollständige Tracking-Pipeline aus"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        print("🚀 Starte Tracking Pipeline")

        # 1. Marker Helper
        bpy.ops.clip.marker_helper_main()

        # 2. Proxy deaktivieren
        bpy.ops.clip.disable_proxy()

        # 3. Detect
        bpy.ops.clip.detect()

        # 4. Proxy aktivieren
        bpy.ops.clip.enable_proxy()

        # 5. Bidirektionales Tracking
        bpy.ops.clip.bidirectional_track()

        # 6. Clean Short Tracks (verzögert über Timer)
        bpy.app.timers.register(wait_for_tracking_stability, first_interval=1.0)

        self.report({'INFO'}, "Tracking gestartet. Clean läuft automatisch nach Abschluss.")
        return {'FINISHED'}
