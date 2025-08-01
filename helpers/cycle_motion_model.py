import bpy

def cycle_motion_model():
    """Cycle the default motion model used for newly added tracks."""
    area = next((a for a in bpy.context.screen.areas if a.type == "CLIP_EDITOR"), None)
    if area is None:
        print("⚠️ Kein Clip-Editor gefunden.")
        return

    clip = area.spaces.active.clip
    if clip is None:
        print("⚠️ Kein Clip geladen.")
        return

    tracking = clip.tracking
    tracking_object = tracking.objects.active
    if tracking_object is None:
        print("⚠️ Kein aktives Tracking-Objekt.")
        return

    settings = tracking_object.settings
    models = ["Perspective", "Affine", "LocRotScale", "Loc"]
    current = settings.motion_model

    try:
        next_index = (models.index(current) + 1) % len(models)
    except ValueError:
        next_index = 0

    settings.motion_model = models[next_index]
    print(f"✅ Standard-Motion-Model geändert zu: {models[next_index]}")


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
