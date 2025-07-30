import bpy


def track_markers_until_end() -> None:
    """Track selected markers forward until the end frame."""
    scene = bpy.context.scene
    space = bpy.context.space_data
    clip = space.clip if space and space.type == 'CLIP_EDITOR' else None

    if not clip:
        print("❌ Kein Clip aktiv oder falscher Editor.")
        return

    result = bpy.ops.clip.track_markers(
        'INVOKE_DEFAULT',
        backwards=False,
        sequence=True,
    )

    if 'CANCELLED' in result:
        print("❌ Tracking abgebrochen.")
    else:
        print("✅ Tracking gestartet (Sequenzmodus).")
