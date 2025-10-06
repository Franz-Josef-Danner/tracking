import bpy

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    bpy.ops.clip.track_markers(*, backwards=False, sequence=False)
Track selected markers

Parameters:
backwards (boolean, (optional)) – Backwards, Do backwards tracking

sequence (boolean, (optional)) – Track Sequence, Track marker during image sequence rather than single image