# Datei: helpers/cycle_motion_model.py

import bpy

def cycle_motion_model():
    """Zyklisch den Motion-Model-Typ wechseln (für neu zu erstellende Tracker)."""
    clip = bpy.context.edit_movieclip
    if clip is None:
        print("⚠️ Kein aktiver MovieClip.")
        return

    settings = clip.tracking.settings

    model_items = settings.bl_rna.properties['default_motion_model'].enum_items
    models = [item.identifier for item in model_items]

    if not models:
        print("⚠️ Keine Motion Models verfügbar.")
        return

    current_model = settings.default_motion_model
    try:
        idx = models.index(current_model)
    except ValueError:
        idx = -1

    next_idx = (idx + 1) % len(models)
    next_model = models[next_idx]
    settings.default_motion_model = next_model

    print(f"✅ Motion Model gewechselt zu: {next_model}")


class TRACKING_OT_cycle_motion_model(bpy.types.Operator):
    """Cycle default motion model used for new tracks"""
    bl_idname = "tracking.cycle_motion_model"
    bl_label = "Cycle Motion Model"
    bl_description = "Zyklisch den Motion-Model-Typ wechseln für neue Tracker"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.space_data is not None and
            context.space_data.type == 'CLIP_EDITOR' and
            context.edit_movieclip is not None
        )

    def execute(self, context):
        cycle_motion_model()
        self.report({'INFO'}, "Motion Model geändert")
        return {'FINISHED'}
