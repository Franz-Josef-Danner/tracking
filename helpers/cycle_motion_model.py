import bpy


def cycle_motion_model() -> None:
    """Toggle the motion model of the active clip."""
    area = next(
        (a for a in bpy.context.screen.areas if a.type == "CLIP_EDITOR"),
        None,
    )
    if area is None:
        print("⚠️ Kein Clip-Editor gefunden")
        return
    clip = area.spaces.active.clip
    if clip is None:
        print("⚠️ Kein Clip geladen")
        return
    tracking = clip.tracking
    model = tracking.settings.motion_model
    tracking.settings.motion_model = (
        "Affine" if model != "Affine" else "Perspective"
    )
    print(f"🔄 Motion Model gewechselt: {model} → {tracking.settings.motion_model}")


class TRACKING_OT_cycle_motion_model(bpy.types.Operator):
    bl_idname = "tracking.cycle_motion_model"
    bl_label = "Cycle Motion Model"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        cycle_motion_model()
        return {"FINISHED"}
