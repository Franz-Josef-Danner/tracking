import bpy


def detect_features(context, values):
    # Anwenden dynamischer Pattern Size während Iteration (verbesserte Qualität)
    clip = context.edit_movieclip
    clip.tracking.settings.pattern_size = int(max(5, values["pz"]))

    bpy.ops.clip.detect_features(
        placement='FRAME',
        margin=values["ma"],
        threshold=values["tr"],
        min_distance=values["md"],
    )
