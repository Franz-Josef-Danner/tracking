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
    "version": (1, 1, 0),
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
        min_new = context.scene.min_marker_count
        tracks_before = len(clip.tracking.tracks)

        print(
            f"[Detect] Running detection for {min_new} markers at "
            f"threshold {threshold:.4f}"
        )
        initial_names = {t.name for t in clip.tracking.tracks}
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=50,
            min_distance=100,
            placement='FRAME',
        )
        for track in clip.tracking.tracks:
            if track.name not in initial_names and not track.name.startswith("TRACK_"):
                track.name = f"TRACK_{track.name}"
        tracks_after = len(clip.tracking.tracks)

        while (tracks_after - tracks_before) < min_new and threshold > 0.0001:
            factor = ((tracks_after - tracks_before) + 0.1) / min_new
            threshold *= factor
            print(
                f"[Detect] Only {tracks_after - tracks_before} found, "
                f"lowering threshold to {threshold:.4f}"
            )
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=50,
                min_distance=100,
                placement='FRAME',
            )
            for track in clip.tracking.tracks:
                if track.name not in initial_names and not track.name.startswith("TRACK_"):
                    track.name = f"TRACK_{track.name}"
            tracks_after = len(clip.tracking.tracks)

        print(
            f"[Detect] Finished with {tracks_after - tracks_before} new markers"
        )
        return {'FINISHED'}


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


# ---- Delete Short Tracks Operator (from Track Length.py) ----
class TRACKING_OT_delete_short_tracks_with_prefix(bpy.types.Operator):
    """Remove tracks with prefix ``TRACK_`` shorter than 25 frames."""

    bl_idname = "tracking.delete_short_tracks_with_prefix"
    bl_label = "Delete Short Tracks with Prefix"

    def execute(self, context):
        print("\n=== [Delete short tracks] ===")
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "No clip loaded")
            print("[Delete] No movie clip loaded")
            return {'CANCELLED'}

        active_obj = clip.tracking.objects.active
        tracks = active_obj.tracks
        tracks_to_delete = [
            t for t in tracks if t.name.startswith("TRACK_") and len(t.markers) < 25
        ]

        for track in tracks:
            track.select = track in tracks_to_delete

        if not tracks_to_delete:
            self.report({'INFO'}, "No short tracks found with prefix 'TRACK_'")
            return {'CANCELLED'}

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                with context.temp_override(
                                    area=area, region=region, space_data=space
                                ):
                                    bpy.ops.clip.delete_track()
                                for track in active_obj.tracks:
                                    if track.name.startswith("TRACK_"):
                                        track.name = track.name.replace("TRACK_", "GOOD_", 1)
                                self.report(
                                    {'INFO'},
                                    f"Deleted {len(tracks_to_delete)} short tracks with prefix 'TRACK_'",
                                )
                                return {'FINISHED'}

        self.report({'ERROR'}, "No Clip Editor area found")
        return {'CANCELLED'}


class TRACKING_PT_custom_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Custom Tracking Tools'

    def draw(self, context):
        layout = self.layout
        layout.operator(TRACKING_OT_delete_short_tracks_with_prefix.bl_idname)

# ---- Playhead utilities (from playhead.py) ----
DEFAULT_MINIMUM_MARKER_COUNT = 5

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
    _threshold = DEFAULT_MINIMUM_MARKER_COUNT
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

            context.scene.tracking_cycle_status = "Searching next frame"
            marker_counts = get_tracking_marker_counts()
            target_frame = find_frame_with_few_tracking_markers(
                marker_counts,
                self._threshold,
            )
            set_playhead(target_frame)

            if target_frame is None:
                self.report({'INFO'}, "Tracking cycle complete")
                context.scene.tracking_cycle_status = "Finished"
                self.cancel(context)
                return {'FINISHED'}

            for track in self._clip.tracking.tracks:
                track.select = False

            print(
                f"[Cycle] Detecting features and tracking "
                f"(min markers {context.scene.min_marker_count})"
            )
            context.scene.tracking_cycle_status = "Detecting features"
            bpy.ops.clip.detect_features_custom()
            context.scene.tracking_cycle_status = "Tracking markers"
            bpy.ops.clip.auto_track_forward()
            context.scene.tracking_cycle_status = "Cleaning tracks"
            bpy.ops.tracking.delete_short_tracks_with_prefix()
            self._last_frame = context.scene.frame_current
            print(f"[Cycle] Step finished at frame {self._last_frame}")
            context.scene.tracking_cycle_status = "Running"

        elif event.type == 'ESC':
            self.report({'INFO'}, "Tracking cycle cancelled")
            print("[Cycle] Cancelled by user")
            context.scene.tracking_cycle_status = "Cancelled"
            self.cancel(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        print(
            f"[Cycle] Starting tracking cycle "
            f"(min_marker_count={context.scene.min_marker_count})"
        )
        context.scene.tracking_cycle_status = "Running"
        self._clip = context.space_data.clip
        if not self._clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            print("[Cycle] No clip found")
            return {'CANCELLED'}

        self._threshold = context.scene.min_marker_count
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
        layout.prop(context.scene, "min_marker_count")
        layout.label(text=context.scene.tracking_cycle_status)
        layout.operator(
            CLIP_OT_tracking_cycle.bl_idname,
            icon='REC',
        )

# ---- Registration ----
classes = [
    DetectFeaturesCustomOperator,
    TRACK_OT_auto_track_forward,
    TRACKING_OT_delete_short_tracks_with_prefix,
    TRACKING_PT_custom_panel,
    CLIP_OT_tracking_cycle,
    CLIP_PT_tracking_cycle_panel,
]

def register():
    """Register all classes and ensure required modules are loaded."""

    bpy.types.Scene.min_marker_count = bpy.props.IntProperty(
        name="Min Marker Count",
        default=DEFAULT_MINIMUM_MARKER_COUNT,
        min=1,
        description="Minimum markers for detection and search",
    )

    bpy.types.Scene.tracking_cycle_status = bpy.props.StringProperty(
        name="Tracking Status",
        default="Idle",
        description="Current state of the tracking cycle",
    )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister all classes."""

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.tracking_cycle_status

if __name__ == "__main__":
    register()
