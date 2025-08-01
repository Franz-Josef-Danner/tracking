import bpy

def run_tracking_optimization(context):
    """Löst den Operator aus track_default_settings.py aus."""
    result = bpy.ops.clip.track_default_settings()
    return result
