"""Combine feature detection, tracking and playhead search in one cycle.

This script can be run directly from Blender's text editor or installed as
an add-on. It imports the existing operators from ``detect.py`` and
``track.py`` and provides a single button in the Movie Clip Editor that
repeats the sequence ``Playhead -> Detect -> Track`` until no further frame
with too few markers is found.
"""

bl_info = {
    "name": "Tracking Cycle",
    "blender": (2, 80, 0),
    "category": "Clip",
}

import bpy
from collections import Counter

# ---- Feature Detection Operator (from detect.py) ----
class DetectFeaturesCustomOperator(bpy.types.Operator):
    """Wrapper for ``bpy.ops.clip.detect_features`` with fixed settings."""

    bl_idname = "clip.detect_features_custom"
    bl_label = "Detect Features (Custom)"

    def execute(self, context):
        bpy.ops.clip.detect_features(
            threshold=0.01,
            margin=500,
            min_distance=10,
            placement='FRAME'
        )
        return {'FINISHED'}

class CLIP_PT_DetectFeaturesPanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Detect Features Tool"

    def draw(self, context):
        self.layout.operator(
            DetectFeaturesCustomOperator.bl_idname,
            icon='VIEWZOOM',
        )

# ---- Auto Track Operator (from track.py) ----
class TRACK_OT_auto_track_forward(bpy.types.Operator):
    """Automatically track markers that start with ``TRACK_`` forward."""

    bl_idname = "clip.auto_track_forward"
    bl_label = "Auto Track TRACK_ Markers"
    bl_description = "Selektiert TRACK_-Marker und trackt sie automatisch vorwärts"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        tracking = clip.tracking
        tracks = tracking.tracks

        for track in tracks:
            track.select = track.name.startswith("TRACK_")

        bpy.ops.clip.track_markers(sequence=True)
        return {'FINISHED'}

class TRACK_PT_auto_track_panel(bpy.types.Panel):
    """UI panel for the auto-track operator."""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = "Auto TRACK_"

    def draw(self, context):
        layout = self.layout
        layout.operator(TRACK_OT_auto_track_forward.bl_idname, icon='TRACKING_FORWARDS')

# ---- Playhead utilities (from playhead.py) ----
MINIMUM_MARKER_COUNT = 5

def get_tracking_marker_counts():
    """Return a mapping of frame numbers to the number of markers."""

    marker_counts = Counter()
    for clip in bpy.data.movieclips:
        for track in clip.tracking.tracks:
            for marker in track.markers:
                frame = marker.frame
                marker_counts[frame] += 1
    return marker_counts

def find_frame_with_few_tracking_markers(marker_counts, minimum_count):
    """Return the first frame with fewer markers than ``minimum_count``."""

    start = bpy.context.scene.frame_start
    end = bpy.context.scene.frame_end
    for frame in range(start, end + 1):
        if marker_counts.get(frame, 0) < minimum_count:
            return frame
    return None

def set_playhead(frame):
    """Set the current frame if ``frame`` is valid."""

    if frame is not None:
        bpy.context.scene.frame_current = frame

# ---- Cycle Operator ----
class CLIP_OT_tracking_cycle(bpy.types.Operator):
    """Cycle through frames to detect and track until finished."""

    bl_idname = "clip.tracking_cycle"
    bl_label = "Start Tracking Cycle"
    bl_description = "Find frames, detect and track iteratively"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        while True:
            marker_counts = get_tracking_marker_counts()
            target_frame = find_frame_with_few_tracking_markers(marker_counts, MINIMUM_MARKER_COUNT)
            set_playhead(target_frame)

            if target_frame is None:
                break

            bpy.ops.clip.detect_features_custom()
            bpy.ops.clip.auto_track_forward()

        self.report({'INFO'}, "Tracking cycle complete")
        return {'FINISHED'}

class CLIP_PT_tracking_cycle_panel(bpy.types.Panel):
    """UI panel exposing the tracking cycle operator."""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Tracking Cycle"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            CLIP_OT_tracking_cycle.bl_idname,
            icon='REC',
        )

# ---- Registration ----
classes = [
    DetectFeaturesCustomOperator,
    CLIP_PT_DetectFeaturesPanel,
    TRACK_OT_auto_track_forward,
    TRACK_PT_auto_track_panel,
    CLIP_OT_tracking_cycle,
    CLIP_PT_tracking_cycle_panel,
]

def register():
    """Register all classes and ensure required modules are loaded."""

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister all classes."""

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
