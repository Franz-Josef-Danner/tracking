import bpy
from ...helpers.marker_helpers import ensure_valid_selection
from ...helpers.tracking_helpers import track_markers_range


def execute(self, context):
    """Track selected markers backwards then forwards within scene range."""
    scene = context.scene
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return {'CANCELLED'}

    if not ensure_valid_selection(clip, scene.frame_current):
        self.report({'WARNING'}, "Keine gültigen Marker ausgewählt")
        return {'CANCELLED'}

    original_start = scene.frame_start
    original_end = scene.frame_end
    current = scene.frame_current

    print(f"[Track Partial] current {current} start {original_start} end {original_end}")

    clip.use_proxy = True

    if bpy.ops.clip.track_markers.poll():
        print("[Track Partial] track backwards")
        track_markers_range(scene, original_start, current, current, True)

        print("[Track Partial] track forwards")
        track_markers_range(scene, current, original_end, current, False)

    print(f"[Track Partial] done at frame {scene.frame_current}")

    scene.frame_start = original_start
    scene.frame_end = original_end

    return {'FINISHED'}
