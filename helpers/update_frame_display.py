import bpy


def update_frame_display(context=None):
    """Sync the Clip Editor to the scene frame and redraw."""
    if context is None:
        context = bpy.context
    space = context.space_data
    if hasattr(space, "clip_user"):
        space.clip_user.frame_current = context.scene.frame_current
    if context.area:
        context.area.tag_redraw()
