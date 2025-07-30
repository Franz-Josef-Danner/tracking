import bpy


def cycle_motion_model() -> None:
    """Cycle the default motion model for newly created markers."""
    models = ["Loc", "LocRot", "LocScale", "Affine", "Perspective"]

    scene_settings = bpy.context.scene.tracking_settings
    current = scene_settings.motion_model

    try:
        index = models.index(current)
        next_model = models[(index + 1) % len(models)]
        scene_settings.motion_model = next_model
        print(f"🔄 Motion Model gewechselt: {current} → {next_model}")
    except ValueError:
        print(f"⚠️ Ungültiger Motion-Model-Wert: {current}")
