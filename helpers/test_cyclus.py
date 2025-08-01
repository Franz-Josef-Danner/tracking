import bpy

def run_default_tracking_settings(context):
    """Führt den Operator 'clip.track_default_settings' aus."""
    try:
        bpy.ops.clip.track_default_settings()
        print("Operator erfolgreich ausgeführt.")
    except Exception as e:
        print(f"Fehler beim Ausführen von track_default_settings: {e}")
