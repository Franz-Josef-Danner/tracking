import bpy
from mathutils import Vector

def set_test_value(context):
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    pattern_size = 10
    search_size = pattern_size * 2

    for track in tracks:
        if track.select:
            track.pattern_size = Vector((pattern_size, pattern_size))
            track.search_size = Vector((search_size, search_size))
            print(f"[SetSizes] Track '{track.name}': Pattern={track.pattern_size}, Search={track.search_size}")
