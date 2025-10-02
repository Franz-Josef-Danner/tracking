import bpy

def detect_features(context, values):
    clip = context.edit_movieclip
    if clip is None:
        return 0
    # Versuche Features zu detektieren
    res = bpy.ops.clip.detect_features(
        placement='FRAME',
        margin=values["ma"],
        threshold=values["tr"],
        min_distance=values["md"]
    )
    return res
