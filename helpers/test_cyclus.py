import bpy


def run_default_tracking_settings(context):
    """Apply Blender's default tracking settings."""
    bpy.ops.clip.tracking_default_settings('INVOKE_DEFAULT')
