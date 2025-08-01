"""Helper to trigger the add-on's default tracking settings."""

import bpy


def run_default_tracking_settings(context):
    """Execute the operator that sets default tracking values."""
    bpy.ops.tracking.set_default_settings()
