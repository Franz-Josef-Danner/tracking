import bpy

def detect_features(context, values):
    clip = context.edit_movieclip
    if clip is None:
        return 0

    # Blender erwartet Ganzzahlen für margin und min_distance.
    margin = max(1, int(round(values["ma"])))
    min_distance = max(1, int(round(values["md"])))

    res = bpy.ops.clip.detect_features(
        placement='FRAME',
        margin=margin,
        threshold=float(values["tr"]),  # threshold darf float bleiben
        min_distance=min_distance
    )
    return res
