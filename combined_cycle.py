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
    "version": (1, 2, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

import bpy
from collections import Counter
import os


def ensure_margin_distance(clip):
    """Return margin and distance based on the clip width.

    The values are cached on the clip as custom properties to avoid
    recalculating them every time detection runs.
    """

    if "MARGIN" in clip and "DISTANCE" in clip:
        # Cast to int in case previous versions stored floats
        return int(clip["MARGIN"]), int(clip["DISTANCE"])

    width = clip.size[0]
    margin = max(1, int(width / 200))
    distance = max(1, int(width / 20))
    clip["MARGIN"] = margin
    clip["DISTANCE"] = distance
    return margin, distance


def update_min_marker_props(scene, context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    scene.min_marker_count_plus = base * 4
    scene.min_marker_count_plus_min = int(scene.min_marker_count_plus * 0.8)
    scene.min_marker_count_plus_max = int(scene.min_marker_count_plus * 1.2)


# Try to initialize margin and distance on the active clip when the
# script is executed directly. This mirrors the standalone helper
# script and ensures the values are available before detection runs.
try:
    area = next((a for a in bpy.context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if area:
        space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
        if space and space.clip:
            ensure_margin_distance(space.clip)
except Exception:
    # When running headless there may be no UI yet; ignore errors.
    pass




class ToggleProxyOperator(bpy.types.Operator):
    """Proxy/Timecode Umschalten"""

    bl_idname = "clip.toggle_proxy"
    bl_label = "Toggle Proxy/Timecode"

    def execute(self, context):
        clip = context.space_data.clip
        if clip:
            clip.use_proxy = not clip.use_proxy
            self.report({'INFO'}, f"Proxy/Timecode {'aktiviert' if clip.use_proxy else 'deaktiviert'}")
        else:
            self.report({'WARNING'}, "Kein Clip geladen")
        return {'FINISHED'}

# ---- Cache Clearing Operator (from catch clean.py) ----
class CLIP_PT_clear_cache_panel(bpy.types.Panel):
    """UI panel providing a button to clear the RAM cache."""

    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Cache Tools'
    bl_label = 'Clear Cache'

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "clip.clear_custom_cache",
            text="Clear RAM Cache",
            icon='TRASH',
        )


class CLIP_OT_clear_custom_cache(bpy.types.Operator):
    """Reload the active clip to clear its RAM cache."""

    bl_idname = "clip.clear_custom_cache"
    bl_label = "Clear RAM Cache"
    bl_description = "Reloads the clip to clear its RAM cache"

    def execute(self, context):
        sc = context.space_data
        if sc and sc.clip:
            bpy.ops.clip.reload()
            self.report({'INFO'}, f"RAM-Cache für Clip '{sc.clip.name}' wurde geleert")
            return {'FINISHED'}
        self.report({'WARNING'}, "Kein Clip aktiv im Editor")
        return {'CANCELLED'}


class CLIP_OT_auto_start(bpy.types.Operator):
    """Build a 50% proxy and start the tracking cycle."""

    bl_idname = "clip.auto_start_tracking"
    bl_label = "Auto Start"

    _timer = None
    _clip = None

    def modal(self, context, event):
        if event.type == 'TIMER' and self._clip:
            proxy_done = not getattr(self._clip, "is_proxy_building", False)
            if proxy_done:
                context.window_manager.event_timer_remove(self._timer)
                context.scene.proxy_built = True
                self.report({'INFO'}, "✅ Proxy-Erstellung abgeschlossen")
                bpy.ops.clip.tracking_cycle('INVOKE_DEFAULT')
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        context.scene.proxy_built = False

        clip.use_proxy = True
        proxy = clip.proxy
        proxy.quality = 50
        proxy.directory = bpy.path.abspath("//BL_proxy/")
        proxy.timecode = 'FREE_RUN_NO_GAPS'

        proxy.build_25 = proxy.build_50 = proxy.build_75 = proxy.build_100 = False
        proxy.build_50 = True

        proxy.build_undistorted_25 = False
        proxy.build_undistorted_50 = False
        proxy.build_undistorted_75 = False
        proxy.build_undistorted_100 = False

        override = context.copy()
        override['area'] = next(
            area for area in context.screen.areas if area.type == 'CLIP_EDITOR'
        )
        override['region'] = next(
            region for region in override['area'].regions if region.type == 'WINDOW'
        )
        override['space_data'] = override['area'].spaces.active
        override['clip'] = clip

        with context.temp_override(**override):
            bpy.ops.clip.rebuild_proxy()

        self._clip = clip
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        self.report({'INFO'}, "Proxy 50% Erstellung gestartet")
        return {'RUNNING_MODAL'}

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
            return {'CANCELLED'}

        toggled = False
        if context.scene.proxy_built and clip.use_proxy:
            bpy.ops.clip.toggle_proxy()
            toggled = True

        threshold = 0.1
        min_new = context.scene.min_marker_count_plus_min
        max_new = context.scene.min_marker_count_plus_max
        tracks_before = len(clip.tracking.tracks)

        # Ensure margin and distance values are available for this clip
        margin, distance = ensure_margin_distance(clip)

        base = context.scene.min_marker_count
        print(
            f"[Detect] frame {context.scene.frame_current} in '{clip.name}' "
            f"({clip.size[0]}x{clip.size[1]})"
        )
        print(
            f"[Detect] base {base}, expected range {min_new}-{max_new} "
            f"starting at threshold {threshold:.4f}"
        )
        attempt = 0
        max_attempts = 5
        tracks_after = tracks_before
        while attempt < max_attempts:
            attempt += 1
            print(
                f"[Detect] attempt {attempt} with threshold {threshold:.4f}"
            )
            initial_names = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
                placement='FRAME',
            )

            new_tracks = [
                t for t in clip.tracking.tracks if t.name not in initial_names
            ]
            for track in new_tracks:
                if not track.name.startswith("TRACK_"):
                    track.name = f"TRACK_{track.name}"

            tracks_after = len(clip.tracking.tracks)
            new_count = tracks_after - tracks_before
            print(f"[Detect] found {new_count} new markers")

            if min_new <= new_count <= max_new:
                print(
                    f"[Detect] attempt {attempt}: "
                    f"{new_count} markers in range"
                )
                break

            # Remove the newly created tracks using the operator to ensure
            # compatibility across Blender versions
            active_obj = clip.tracking.objects.active
            for t in new_tracks:
                t.select = True

            deleted = False
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            for space in area.spaces:
                                if space.type == 'CLIP_EDITOR':
                                    with context.temp_override(
                                        area=area,
                                        region=region,
                                        space_data=space,
                                    ):
                                        bpy.ops.clip.delete_track()
                                    deleted = True
                                    break
                        if deleted:
                            break
                if deleted:
                    break

            if not deleted:
                self.report({'ERROR'}, 'No Clip Editor area found to delete temporary tracks')
                return {'CANCELLED'}

            # Update track count after deleting the temporary tracks
            tracks_after = len(clip.tracking.tracks)
            new_count = tracks_after - tracks_before

            if new_count < min_new:
                base_plus = context.scene.min_marker_count_plus
                factor = (new_count + 0.1) / base_plus
                threshold *= factor
                print(
                    f"[Detect] attempt {attempt}: {new_count} found, "
                    f"lowering to {threshold:.4f}"
                )
            else:
                factor = max_new / max(new_count, 1)
                threshold *= factor
                print(
                    f"[Detect] attempt {attempt}: {new_count} found, "
                    f"raising to {threshold:.4f}"
                )

        final_tracks = len(clip.tracking.tracks)
        final_new = final_tracks - tracks_before
        print(f"[Detect] final new markers {final_new}")

        if toggled:
            bpy.ops.clip.toggle_proxy()
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
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Marker vorhanden")
            return {'CANCELLED'}

        toggled = False
        if context.scene.proxy_built and not clip.use_proxy:
            bpy.ops.clip.toggle_proxy()
            toggled = True

        bpy.ops.clip.track_markers(sequence=True)

        if toggled:
            bpy.ops.clip.toggle_proxy()
        return {'FINISHED'}


# ---- Delete Short Tracks Operator (from Track Length.py) ----
class TRACKING_OT_delete_short_tracks_with_prefix(bpy.types.Operator):
    """Remove tracks with prefix ``TRACK_`` shorter than the given length."""

    bl_idname = "tracking.delete_short_tracks_with_prefix"
    bl_label = "Delete Short Tracks with Prefix"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "No clip loaded")
            return {'CANCELLED'}

        active_obj = clip.tracking.objects.active
        tracks = active_obj.tracks

        min_len = context.scene.min_track_length
        tracks_to_delete = [
            t for t in tracks if t.name.startswith("TRACK_") and len(t.markers) < min_len
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
                                    area=area,
                                    region=region,
                                    space_data=space,
                                ):
                                    bpy.ops.clip.delete_track()
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
# Seconds between timer events during the tracking cycle
CYCLE_TIMER_INTERVAL = 1.0

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
            if self._last_frame is not None and self._last_frame != context.scene.frame_end:
                self._threshold = max(int(self._threshold * 0.9), 1)

            context.scene.tracking_cycle_status = "Searching next frame"
            marker_counts = get_tracking_marker_counts()
            target_frame = find_frame_with_few_tracking_markers(
                marker_counts,
                self._threshold,
            )
            bpy.ops.clip.clear_custom_cache()
            set_playhead(target_frame)
            context.scene.current_cycle_frame = context.scene.frame_current

            if target_frame is None:
                self.report({'INFO'}, "Tracking cycle complete")
                context.scene.tracking_cycle_status = "Finished"
                self.cancel(context)
                return {'FINISHED'}

            for track in self._clip.tracking.tracks:
                track.select = False

            context.scene.tracking_cycle_status = "Detecting features"
            if context.scene.proxy_built:
                bpy.ops.clip.toggle_proxy()
            bpy.ops.clip.detect_features_custom()
            if context.scene.proxy_built:
                bpy.ops.clip.toggle_proxy()
            context.scene.tracking_cycle_status = "Tracking markers"
            bpy.ops.clip.auto_track_forward()
            context.scene.tracking_cycle_status = "Cleaning tracks"
            bpy.ops.tracking.delete_short_tracks_with_prefix()
            self._last_frame = context.scene.frame_current
            context.scene.tracking_cycle_status = "Running"
            context.scene.current_cycle_frame = context.scene.frame_current

        elif event.type == 'ESC':
            self.report({'INFO'}, "Tracking cycle cancelled")
            context.scene.tracking_cycle_status = "Cancelled"
            self.cancel(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        context.scene.tracking_cycle_status = "Running"
        context.scene.total_cycle_frames = (
            context.scene.frame_end - context.scene.frame_start + 1
        )
        context.scene.current_cycle_frame = context.scene.frame_current
        self._clip = context.space_data.clip
        if not self._clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        self._threshold = context.scene.min_marker_count
        self._last_frame = context.scene.frame_current

        wm = context.window_manager
        self._timer = wm.event_timer_add(CYCLE_TIMER_INTERVAL, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None


class CLIP_PT_tracking_cycle_panel(bpy.types.Panel):
    """UI panel exposing the tracking cycle operator."""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Tracking Cycle"

    def draw(self, context):
        layout = self.layout

        layout.prop(context.scene, "min_marker_count")
        layout.prop(context.scene, "min_track_length")
        layout.label(text=context.scene.tracking_cycle_status)
        layout.label(
            text=f"Frame {context.scene.current_cycle_frame}/"
            f"{context.scene.total_cycle_frames}"
        )
        layout.operator(
            CLIP_OT_auto_start.bl_idname,
            icon='REC',
        )

# ---- Registration ----
classes = [
    ToggleProxyOperator,
    CLIP_PT_clear_cache_panel,
    CLIP_OT_clear_custom_cache,
    DetectFeaturesCustomOperator,
    TRACK_OT_auto_track_forward,
    TRACKING_OT_delete_short_tracks_with_prefix,
    CLIP_OT_tracking_cycle,
    CLIP_OT_auto_start,
    CLIP_PT_tracking_cycle_panel,
]

def register():
    """Register all classes and ensure required modules are loaded."""

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.min_marker_count = bpy.props.IntProperty(
        name="Min Marker Count",
        default=DEFAULT_MINIMUM_MARKER_COUNT,
        min=1,
        description="Minimum markers for detection and search",
        update=update_min_marker_props,
    )
    bpy.types.Scene.min_marker_count_plus = bpy.props.IntProperty(
        name="Marker Count Plus",
        default=DEFAULT_MINIMUM_MARKER_COUNT * 4,
    )
    bpy.types.Scene.min_marker_count_plus_min = bpy.props.IntProperty(
        name="Marker Count Plus Min",
        default=int(DEFAULT_MINIMUM_MARKER_COUNT * 4 * 0.8),
    )
    bpy.types.Scene.min_marker_count_plus_max = bpy.props.IntProperty(
        name="Marker Count Plus Max",
        default=int(DEFAULT_MINIMUM_MARKER_COUNT * 4 * 1.2),
    )

    bpy.types.Scene.min_track_length = bpy.props.IntProperty(
        name="Min Track Length",
        default=25,
        min=1,
        description="Minimum track length kept after tracking",
    )

    bpy.types.Scene.proxy_built = bpy.props.BoolProperty(
        name="Proxy Built",
        default=False,
        description="True when a recommended proxy has been built",
    )

    for scene in bpy.data.scenes:
        scene.proxy_built = False
        update_min_marker_props(scene, bpy.context)

    bpy.types.Scene.tracking_cycle_status = bpy.props.StringProperty(
        name="Tracking Status",
        default="Idle",
        description="Current state of the tracking cycle",
    )

    bpy.types.Scene.current_cycle_frame = bpy.props.IntProperty(
        name="Current Cycle Frame",
        default=0,
        description="Current frame processed in the tracking cycle",
    )

    bpy.types.Scene.total_cycle_frames = bpy.props.IntProperty(
        name="Total Cycle Frames",
        default=0,
        description="Total number of frames in the cycle",
    )

    # Pre-calculate margin and distance if a clip is already loaded
    try:
        area = next((a for a in bpy.context.screen.areas if a.type == 'CLIP_EDITOR'), None)
        if area:
            space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
            if space and space.clip:
                ensure_margin_distance(space.clip)
    except Exception:
        # The UI might not be fully ready when registering in background
        pass


def unregister():
    """Unregister all classes."""

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_marker_count_plus
    del bpy.types.Scene.min_marker_count_plus_min
    del bpy.types.Scene.min_marker_count_plus_max
    del bpy.types.Scene.min_track_length
    del bpy.types.Scene.proxy_built
    del bpy.types.Scene.tracking_cycle_status
    del bpy.types.Scene.current_cycle_frame
    del bpy.types.Scene.total_cycle_frames

if __name__ == "__main__":
    register()
