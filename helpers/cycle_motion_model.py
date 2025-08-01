import bpy


def cycle_motion_model() -> None:
    """Cycle through common motion models on the active track."""
    area = next((a for a in bpy.context.screen.areas if a.type == "CLIP_EDITOR"), None)
    if area is None:
        print("⚠️ Kein Clip-Editor gefunden")
        return
    clip = area.spaces.active.clip
    if clip is None:
        print("⚠️ Kein Clip geladen")
        return

    tracking = clip.tracking
    tracking_object = tracking.objects.active
    if tracking_object is None:
        print("⚠️ Kein aktives Tracking-Objekt")
        return

    active_track = tracking_object.tracks.active
    if active_track is None:
        print("⚠️ Kein aktiver Track ausgewählt")
        return

    models = ["Perspective", "Affine", "LocRotScale", "Loc"]
    current = active_track.motion_model

    try:
        next_index = (models.index(current) + 1) % len(models)
    except ValueError:
        next_index = 0

    active_track.motion_model = models[next_index]
    print(f"✅ Motion Model für Track '{active_track.name}' gewechselt zu: {models[next_index]}")


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
