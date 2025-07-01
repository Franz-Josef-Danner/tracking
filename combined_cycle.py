"""Combine feature detection, tracking and playhead search in one cycle.

This script can be run directly from Blender's text editor or installed as
an add-on. It provides a single button in the Movie Clip Editor that
repeats the sequence ``Playhead -> Detect -> Track`` until no further frame
with too few markers is found. After every tracking step the current frame
is compared with the scene end and the threshold for the next search is
reduced by ten percent if the end is not reached. Newly detected markers
are immediately tracked forward.
"""

bl_info = {
    "name": "Tracking Cycle",
    "description": "Find frames, detect and track iteratively",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
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
        """Detect features and lower the threshold if none are found."""

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            print("[Detect] No clip found")
            return {'CANCELLED'}

        threshold = 0.1
        tracks_before = len(clip.tracking.tracks)

        print("[Detect] Running feature detection...")
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=50,
            min_distance=100,
            placement='FRAME',
        )
        tracks_after = len(clip.tracking.tracks)

        while tracks_after == tracks_before and threshold > 0.0001:
            threshold *= 0.9
            print(f"[Detect] No features, threshold -> {threshold:.4f}")
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=50,
                min_distance=100,
                placement='FRAME',
            )
            tracks_after = len(clip.tracking.tracks)

        print("[Detect] Done")
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
    """Track all currently selected markers forward."""

    bl_idname = "clip.auto_track_forward"
    bl_label = "Auto Track Selected"
    bl_description = "Trackt alle ausgewählten Marker automatisch vorwärts"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip = context.space_data.clip
        print("[Track] Starting auto track...")
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Marker vorhanden")
            return {'CANCELLED'}

        bpy.ops.clip.track_markers(sequence=True)
        print("[Track] Finished auto track")
        return {'FINISHED'}

class TRACK_PT_auto_track_panel(bpy.types.Panel):
    """UI panel for the auto-track operator."""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = "Auto Track"

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
    print("[Cycle] Marker count per frame:")
    for frame, count in sorted(marker_counts.items()):
        print(f"  Frame {frame}: {count}")
    return marker_counts

def find_frame_with_few_tracking_markers(marker_counts, minimum_count):
    """Return the first frame with fewer markers than ``minimum_count``."""

    start = bpy.context.scene.frame_start
    end = bpy.context.scene.frame_end
    for frame in range(start, end + 1):
        if marker_counts.get(frame, 0) < minimum_count:
            print(f"[Cycle] Found frame {frame} with {marker_counts.get(frame,0)} markers")
            return frame
    print("[Cycle] No frame below threshold found")
    return None

def set_playhead(frame):
    """Set the current frame if ``frame`` is valid."""

    if frame is not None:
        bpy.context.scene.frame_current = frame
        print(f"[Cycle] Playhead set to frame {frame}")
    else:
        print("[Cycle] No frame to set playhead")

# ---- Cycle Operator ----
class CLIP_OT_tracking_cycle(bpy.types.Operator):
    """Run the tracking cycle step by step using a timer."""

    bl_idname = "clip.tracking_cycle"
    bl_label = "Start Tracking Cycle"
    bl_description = "Find frames, detect and track iteratively"

    _timer = None
    _clip = None
    _threshold = MINIMUM_MARKER_COUNT
    _last_frame = None

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def modal(self, context, event):
        if event.type == 'TIMER':
            print("[Cycle] Timer event")
            if self._last_frame is not None and self._last_frame != context.scene.frame_end:
                self._threshold = max(int(self._threshold * 0.9), 1)
                print(f"[Cycle] Threshold reduced to {self._threshold}")

            marker_counts = get_tracking_marker_counts()
            target_frame = find_frame_with_few_tracking_markers(
                marker_counts,
                self._threshold,
            )
            set_playhead(target_frame)

            if target_frame is None:
                self.report({'INFO'}, "Tracking cycle complete")
                self.cancel(context)
                return {'FINISHED'}

            for track in self._clip.tracking.tracks:
                track.select = False

            print("[Cycle] Detecting features and tracking")
            bpy.ops.clip.detect_features_custom()
            bpy.ops.clip.auto_track_forward()
            self._last_frame = context.scene.frame_current
            print(f"[Cycle] Step finished at frame {self._last_frame}")

        elif event.type == 'ESC':
            self.report({'INFO'}, "Tracking cycle cancelled")
            print("[Cycle] Cancelled by user")
            self.cancel(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        print("[Cycle] Starting tracking cycle")
        self._clip = context.space_data.clip
        if not self._clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            print("[Cycle] No clip found")
            return {'CANCELLED'}

        self._threshold = MINIMUM_MARKER_COUNT
        self._last_frame = context.scene.frame_current

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        print("[Cycle] Modal handler added")
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        print("[Cycle] Timer removed")


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
