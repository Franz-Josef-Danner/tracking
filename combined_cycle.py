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
import math
import mathutils
import time


def get_marker_count_plus(scene):
    """Return stored value or the default derived from the base count."""
    return scene.get("_marker_count_plus", scene.min_marker_count * 4)


def set_marker_count_plus(scene, value):
    """Clamp and store marker count plus based on the base marker count."""
    base = scene.min_marker_count
    value = max(base * 4, min(value, base * 200))
    scene["_marker_count_plus"] = int(value)
    scene.min_marker_count_plus_min = int(value * 0.8)
    scene.min_marker_count_plus_max = int(value * 1.2)

def ensure_margin_distance(clip, threshold=1.0):
    """Return margin and distance scaled by ``threshold`` along with the base distance.

    Base values derived from the clip width are cached on the clip as custom
    properties so they are calculated only once per clip. Each call can then
    scale these base values by the desired detection ``threshold`` using
    ``base * (log10(threshold * 100000) / 5)``.
    """

    if "MARGIN" not in clip or "DISTANCE" not in clip:
        width = clip.size[0]
        clip["MARGIN"] = max(1, int(width / 200))
        clip["DISTANCE"] = max(1, int(width / 20))

    base_margin = int(clip["MARGIN"])
    base_distance = int(clip["DISTANCE"])

    scale = math.log10(threshold * 100000) / 5
    margin = max(1, int(base_margin * scale))
    distance = max(1, int(base_distance * scale))
    return margin, distance, base_distance


def update_min_marker_props(scene, context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    scene.min_marker_count_plus = min(base * 4, base * 200)


def adjust_marker_count_plus(scene, delta):
    """Update marker count plus while clamping to the base value."""

    base_plus = scene.min_marker_count * 4
    new_val = max(base_plus, scene.min_marker_count_plus + delta)
    new_val = min(new_val, scene.min_marker_count * 200)
    scene.min_marker_count_plus = new_val


def remove_close_new_tracks(context, clip, base_distance, threshold):
    """Delete ``NEU_`` tracks too close to existing ``GOOD_`` markers.

    Only tracks with the prefix ``GOOD_`` are considered existing markers.
    The removal distance is derived from ``base_distance`` and ``threshold``
    using the same scaling formula as feature detection. It is half the scaled
    distance converted to normalized clip space. Per-marker distances are
    printed only when ``scene.cleanup_verbose`` is enabled; summary logs are
    always shown. Missing markers are also reported.
    """

    current_frame = context.scene.frame_current
    tracks = clip.tracking.tracks

    neu_tracks = [t for t in tracks if t.name.startswith("NEU_")]
    existing = [t for t in tracks if t.name.startswith("GOOD_")]

    # Filter existing tracks to those with a marker at the current frame
    good_tracks = []
    missing = 0
    for track in existing:
        marker = track.markers.find_frame(current_frame)
        if marker:
            good_tracks.append((track, marker))
        else:
            missing += 1
    if missing:
        print(f"[Cleanup] {missing} GOOD_ tracks lack marker at frame {current_frame}")

    if not neu_tracks or not good_tracks:
        print("[Cleanup] skipping - no GOOD_ or NEU_ tracks")
        return 0

    scale = math.log10(threshold * 100000) / 5
    scaled_dist = max(1, int(base_distance * scale))
    norm_dist = (scaled_dist / 2.0) / clip.size[0]
    print(f"[Cleanup] threshold distance {norm_dist:.5f}")

    to_remove = []
    for neu in neu_tracks:
        neu_marker = neu.markers.find_frame(current_frame)
        if not neu_marker:
            if context.scene.cleanup_verbose:
                print(f"[Cleanup] {neu.name} has no marker at frame {current_frame}")
            continue
        neu_pos = mathutils.Vector(neu_marker.co)
        for good, good_marker in good_tracks:
            good_pos = mathutils.Vector(good_marker.co)
            dist = (neu_pos - good_pos).length
            if context.scene.cleanup_verbose:
                print(f"[Cleanup] {neu.name} vs {good.name}: distance {dist:.5f}")
            if dist < norm_dist:
                print(
                    f"[Cleanup] {neu.name} too close to {good.name} "
                    f"({dist:.5f} < {norm_dist:.5f}) -> remove"
                )
                to_remove.append(neu)
                break

    if not to_remove:
        return 0

    for t in tracks:
        t.select = False
    for t in to_remove:
        t.select = True

    area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        print("[Cleanup] Warning: no Clip Editor area found for deletion")
    else:
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        space = getattr(area, 'spaces', None)
        space = space.active if space else None
        if not region or not space:
            print("[Cleanup] Warning: missing region or space for deletion")
        else:
            with context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.delete_track()

    print(f"[Cleanup] Removed {len(to_remove)} NEU_ tracks")
    return len(to_remove)


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
            time.sleep(0.5)
        else:
            self.report({'WARNING'}, "Kein Clip geladen")
        return {'FINISHED'}



class CLIP_OT_auto_start(bpy.types.Operator):
    """Build a 50% proxy and start the tracking cycle."""

    bl_idname = "clip.auto_start_tracking"
    bl_label = "Auto Start"

    _timer = None
    _clip = None
    _checks = 0
    _proxy_paths = None

    def modal(self, context, event):
        if event.type == 'TIMER' and self._clip and self._proxy_paths:
            self._checks += 1
            if any(os.path.exists(p) for p in self._proxy_paths):
                context.window_manager.event_timer_remove(self._timer)
                context.scene.proxy_built = True
                self.report({'INFO'}, "✅ Proxy-Erstellung abgeschlossen")
                bpy.ops.clip.tracking_cycle('INVOKE_DEFAULT')
                return {'FINISHED'}
            if self._checks > 300:
                context.window_manager.event_timer_remove(self._timer)
                self.report({'WARNING'}, "⚠️ Proxy-Erstellung Zeitüberschreitung")
                return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        context.scene.proxy_built = False
        clip_path = bpy.path.abspath(clip.filepath)
        if not os.path.isfile(clip_path):
            return {'CANCELLED'}

        clip.use_proxy = True
        clip.use_proxy_custom_directory = True
        proxy = clip.proxy
        proxy.quality = 50
        proxy.directory = "//BL_proxy/"
        proxy.timecode = 'FREE_RUN_NO_GAPS'

        proxy.build_25 = proxy.build_50 = proxy.build_75 = proxy.build_100 = False
        proxy.build_50 = True

        proxy.build_undistorted_25 = False
        proxy.build_undistorted_50 = False
        proxy.build_undistorted_75 = False
        proxy.build_undistorted_100 = False

        proxy_dir = bpy.path.abspath(proxy.directory)
        os.makedirs(proxy_dir, exist_ok=True)

        alt_dir = os.path.join(proxy_dir, os.path.basename(clip.filepath))
        for d in (proxy_dir, alt_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.startswith("proxy_"):
                        try:
                            os.remove(os.path.join(d, f))
                        except OSError as err:
                            pass

        # Start proxy rebuild

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


        proxy_file = "proxy_50.avi"
        direct_path = os.path.join(proxy_dir, proxy_file)
        alt_path = os.path.join(proxy_dir, os.path.basename(clip.filepath), proxy_file)

        self._clip = clip
        self._proxy_paths = [direct_path, alt_path]
        self._checks = 0
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

        base = context.scene.min_marker_count
        attempt = 0
        max_attempts = 20
        success = False
        tracks_after = tracks_before
        while attempt < max_attempts:
            attempt += 1
            margin, distance, base_distance = ensure_margin_distance(clip, threshold)
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
                track.name = f"NEU_{track.name}"

            # Remove NEU_ markers too close to existing ones before counting
            removed = remove_close_new_tracks(context, clip, base_distance, threshold)
            print(f"[Detect] distance cleanup removed {removed} markers")

            new_count = sum(
                1 for t in clip.tracking.tracks if t.name.startswith("NEU_")
            )

            if min_new <= new_count <= max_new:
                for t in clip.tracking.tracks:
                    if t.name.startswith("NEU_"):
                        t.name = f"TRACK_{t.name[4:]}"
                success = True
                break

            if new_count < min_new:
                base_plus = context.scene.min_marker_count_plus
                factor = (new_count + 0.1) / base_plus
                threshold = max(threshold * factor, 0.0001)
            else:
                factor = new_count / max(max_new, 1)
                threshold = max(threshold * factor, 0.0001)

            # Remove all temporary NEU_ tracks using the operator
            active_obj = clip.tracking.objects.active
            for t in clip.tracking.tracks:
                t.select = t.name.startswith("NEU_")

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

        if not success:
            active_obj = clip.tracking.objects.active
            for t in clip.tracking.tracks:
                t.select = t.name.startswith("NEU_")

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

        final_tracks = len(clip.tracking.tracks)
        final_new = final_tracks - tracks_before

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

        active_obj = clip.tracking.objects.active
        for track in active_obj.tracks:
            track.select = track.name.startswith("TRACK_")

        toggled = False
        if context.scene.proxy_built and not clip.use_proxy:
            bpy.ops.clip.toggle_proxy()
            toggled = True

        start_frame = context.scene.frame_current
        bpy.ops.clip.track_markers(sequence=True)
        set_playhead(start_frame)

        if toggled:
            bpy.ops.clip.toggle_proxy()
        return {'FINISHED'}


# ---- Delete Short Tracks Operator (from Track Length.py) ----
class TRACKING_OT_delete_short_tracks_with_prefix(bpy.types.Operator):
    """Remove tracks with prefix ``TRACK_`` shorter than the given length.

    After deletion the remaining ``TRACK_`` tracks are renamed to ``GOOD_`` so
    they won't be tracked again in the next cycle.
    """

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

        deleted_count = 0
        if tracks_to_delete:
            for track in tracks:
                track.select = track in tracks_to_delete

            area_found = False
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
                                    area_found = True
                                    break
                        if area_found:
                            break
                if area_found:
                    break

            if not area_found:
                self.report({'ERROR'}, "No Clip Editor area found")
                return {'CANCELLED'}

            deleted_count = len(tracks_to_delete)

        # Rename remaining TRACK_ markers to GOOD_
        renamed_count = 0
        for track in active_obj.tracks:
            if track.name.startswith("TRACK_"):
                track.name = f"GOOD_{track.name[6:]}"
                renamed_count += 1

        self.report(
            {'INFO'},
            f"Deleted {deleted_count} short tracks; renamed {renamed_count} to 'GOOD_'",
        )
        return {'FINISHED'}


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
# Maximum number of attempts on the same frame before aborting
MAX_FRAME_ATTEMPTS = 20
# Highest allowed pattern size when adjusting for repeated frames
PATTERN_SIZE_MAX = 150

# Motion model cycling order used when the playhead stays on the same
# frame. Names follow the Blender API spelling from ``MovieTrackingSettings``.
MOTION_MODEL_SEQUENCE = [
    "Loc",
    "LocRot",
    "LocScale",
    "LocRotScale",
    "Affine",
    "Perspective",
]
DEFAULT_MOTION_MODEL = "Loc"

def cycle_motion_model(settings):
    """Advance ``settings.default_motion_model`` to the next value."""

    current = settings.default_motion_model
    try:
        index = MOTION_MODEL_SEQUENCE.index(current)
    except ValueError:
        # Unknown value; do not change it to avoid breaking user setup
        return
    next_index = (index + 1) % len(MOTION_MODEL_SEQUENCE)
    settings.default_motion_model = MOTION_MODEL_SEQUENCE[next_index]

def reset_motion_model(settings):
    """Reset ``settings.default_motion_model`` to ``DEFAULT_MOTION_MODEL``."""

    settings.default_motion_model = DEFAULT_MOTION_MODEL

def get_tracking_marker_counts(clip=None):
    """Return a mapping of frame numbers to the number of markers.

    If ``clip`` is ``None``, the active clip from ``bpy.context`` is used.
    """

    if clip is None:
        clip = bpy.context.space_data.clip
        if not clip:
            return Counter()

    marker_counts = Counter()
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

def set_playhead(frame, retries=2):
    """Position the playhead reliably at ``frame`` and refresh the UI."""

    if frame is None:
        return

    scene = bpy.context.scene
    for _ in range(retries):
        scene.frame_set(frame)
        if scene.frame_current == frame:
            break
        scene.frame_current = frame
        if scene.frame_current == frame:
            break
    else:
        pass

    # Ensure UI reflects the new playhead position
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                area.tag_redraw()

# ---- Cycle Operator ----
class CLIP_OT_tracking_cycle(bpy.types.Operator):
    """Run the tracking cycle step by step using a timer.

    When the playhead is positioned on the same frame as in the previous
    tracking iteration the default pattern size is increased by ten percent. If
    a new frame is reached it is decreased by ten percent again. The search size
    is always set to twice the current pattern size. The pattern size never
    exceeds 150.
    """

    bl_idname = "clip.tracking_cycle"
    bl_label = "Start Tracking Cycle"
    bl_description = "Find frames, detect and track iteratively"

    _timer = None
    _clip = None
    _threshold = DEFAULT_MINIMUM_MARKER_COUNT
    _last_frame = None
    _visited_frames = None
    _current_target = None
    _target_attempts = 0
    _pattern_size = 0
    _original_pattern_size = 0
    _original_search_size = 0

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._last_frame is not None and self._last_frame != context.scene.frame_end:
                self._threshold = max(int(self._threshold * 0.9), 1)

            context.scene.tracking_cycle_status = "Searching next frame"
            marker_counts = get_tracking_marker_counts(self._clip)
            target_frame = find_frame_with_few_tracking_markers(
                marker_counts,
                self._threshold,
            )
            if target_frame is not None:
                if target_frame == self._current_target:
                    self._target_attempts += 1
                else:
                    self._current_target = target_frame
                    self._target_attempts = 1

                if self._target_attempts > MAX_FRAME_ATTEMPTS:
                    settings = self._clip.tracking.settings
                    target_frame = min(target_frame + 1, context.scene.frame_end)
                    self._current_target = target_frame
                    self._target_attempts = 1
                    self._last_frame = None
                    self._pattern_size = max(
                        1,
                        min(PATTERN_SIZE_MAX, int(self._pattern_size / 1.1)),
                    )
                    reset_motion_model(settings)

                if target_frame in self._visited_frames:
                    adjust_marker_count_plus(context.scene, 10)
                else:
                    adjust_marker_count_plus(context.scene, -10)
                    self._visited_frames.add(target_frame)

            if target_frame is not None:
                settings = self._clip.tracking.settings
                if target_frame == self._last_frame:
                    self._pattern_size = max(
                        1,
                        min(PATTERN_SIZE_MAX, int(self._pattern_size * 1.1)),
                    )
                    cycle_motion_model(settings)
                else:
                    self._pattern_size = max(
                        1,
                        min(PATTERN_SIZE_MAX, int(self._pattern_size / 1.1)),
                    )
                    reset_motion_model(settings)
                settings.default_pattern_size = self._pattern_size
                settings.default_search_size = self._pattern_size * 2

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

        settings = self._clip.tracking.settings
        self._original_pattern_size = settings.default_pattern_size
        self._original_search_size = settings.default_search_size
        self._pattern_size = settings.default_pattern_size

        self._threshold = context.scene.min_marker_count
        self._last_frame = context.scene.frame_current
        self._visited_frames = set()
        self._current_target = None
        self._target_attempts = 0
        update_min_marker_props(context.scene, context)

        wm = context.window_manager
        self._timer = wm.event_timer_add(CYCLE_TIMER_INTERVAL, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        if self._clip:
            settings = self._clip.tracking.settings
            settings.default_pattern_size = self._original_pattern_size
            settings.default_search_size = self._original_search_size
        update_min_marker_props(context.scene, context)


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
        min=5,
        max=50,
        description="Minimum markers for detection and search",
        update=update_min_marker_props,
    )
    bpy.types.Scene.min_marker_count_plus = bpy.props.IntProperty(
        name="Marker Count Plus",
        default=DEFAULT_MINIMUM_MARKER_COUNT * 4,
        get=get_marker_count_plus,
        set=set_marker_count_plus,
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

    bpy.types.Scene.cleanup_verbose = bpy.props.BoolProperty(
        name="Cleanup Verbose",
        default=False,
        description="Print per-marker distances during cleanup",
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
    del bpy.types.Scene.cleanup_verbose
    del bpy.types.Scene.tracking_cycle_status
    del bpy.types.Scene.current_cycle_frame
    del bpy.types.Scene.total_cycle_frames

if __name__ == "__main__":
    register()
