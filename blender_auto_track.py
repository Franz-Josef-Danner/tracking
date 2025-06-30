bl_info = {
    "name": "Auto Track Tools",
    "blender": (2, 80, 0),
    "category": "Clip",
    "author": "Auto Generated",
    "version": (1, 3, 0),
    "description": (
        "Provide an Auto Track panel with configurable tracking settings"
    ),
}

import bpy

# Keep track of validated tracks and the last group of detected tracks
GOOD_MARKERS = []
TRACK_MARKERS = []

class AutoTrackProperties(bpy.types.PropertyGroup):
    """Properties stored in the scene for auto tracking"""

    min_marker_count: bpy.props.IntProperty(
        name="Minimum Marker Count",
        description="Minimum number of markers required before tracking",
        default=10,
        min=0,
    )

    min_tracking_length: bpy.props.IntProperty(
        name="Minimum Tracking Length",
        description="Minimum length of a track in frames",
        default=10,
        min=0,
    )

    @property
    def min_marker_multiplier(self):
        """Four times the minimum marker count"""
        return self.min_marker_count * 4

    @property
    def min_marker_count_plus_small(self):
        """Minimum marker count at 80 percent"""
        return int(self.min_marker_multiplier * 0.8)

    @property
    def min_marker_count_plus_big(self):
        """Minimum marker count increased by 20 percent"""
        return int(self.min_marker_multiplier * 1.2)

    margin: bpy.props.IntProperty(
        name="Margin",
        description="Horizontal resolution / 200 for later use",
        default=0,
        min=0,
    )

    min_distance: bpy.props.IntProperty(
        name="Min Distance",
        description="Horizontal resolution / 20 for later use",
        default=0,
        min=0,
    )

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Feature detection threshold",
        default=1.0,
        min=0.0,
        max=1.0,
    )


def remove_track_by_name(tracks, name):
    """Safely remove a track using Blender's delete operator."""
    track = tracks.get(name)
    if not track:
        return

    # Deselect all tracks and select only the target to ensure the operator
    # deletes the correct one. Using the operator avoids issues with
    # ``tracks.remove`` not being available in all Blender versions.
    for t in tracks:
        t.select = False
    track.select = True

    bpy.ops.clip.tracks_delete()


def find_frame_with_few_markers(clip, minimum):
    """Return the first frame with fewer active markers than minimum."""
    start = int(clip.frame_start)
    end = int(clip.frame_start + clip.frame_duration - 1)
    tracks = clip.tracking.tracks
    for frame in range(start, end + 1):
        count = 0
        for track in tracks:
            marker = track.markers.find_frame(frame)
            if marker and not marker.mute:
                count += 1
        if count < minimum:
            return frame
    return None


def auto_track_wrapper(context):
    """Search for sparse marker frames and run Detect Features.

    Returns a tuple of the frame used for detection and information about
    newly created markers. Each entry contains the track name and the
    marker position as ``(x, y)`` at the detection frame. If the number of
    new markers is outside the configured bounds, all newly created tracks
    are removed and an empty list is returned."""

    space = context.space_data
    if not (space and space.clip):
        return None, []

    props = context.scene.auto_track_settings
    frame = find_frame_with_few_markers(space.clip, props.min_marker_count)
    if frame is None:
        return None, []

    clip = space.clip
    tracks = clip.tracking.tracks
    existing = {t.name for t in tracks}

    context.scene.frame_current = frame
    bpy.ops.clip.detect_features(
        threshold=props.threshold,
        margin=props.margin,
        min_distance=props.min_distance,
    )

    new_tracks = [t for t in tracks if t.name not in existing]
    detected = []
    width, height = clip.size

    # Gather coordinates of good markers at this frame
    good_positions = []
    for name in GOOD_MARKERS:
        good = tracks.get(name)
        if not good:
            continue
        mark = good.markers.find_frame(frame)
        if mark:
            good_positions.append((mark.co[0] * width, mark.co[1] * height))

    for track in new_tracks:
        marker = track.markers.find_frame(frame)
        if not marker and track.markers:
            marker = track.markers[0]
        if not marker:
            continue

        x = marker.co[0] * width
        y = marker.co[1] * height
        keep = True
        for gx, gy in good_positions:
            dist = ((x - gx) ** 2 + (y - gy) ** 2) ** 0.5
            if dist < props.min_distance:
                keep = False
                break

        if keep:
            detected.append((track, (marker.co[0], marker.co[1])))
        else:
            remove_track_by_name(tracks, track.name)

    TRACK_MARKERS[:] = [t.name for t, _ in detected]

    if (
        len(detected) < props.min_marker_count_plus_small
        or len(detected) > props.min_marker_count_plus_big
    ):
        for track, _ in detected:
            remove_track_by_name(tracks, track.name)
        TRACK_MARKERS.clear()
        return frame, []

    GOOD_MARKERS.extend(TRACK_MARKERS)
    return frame, [(t.name, pos) for t, pos in detected]


class CLIP_OT_auto_track_settings(bpy.types.Operator):
    """Show the auto track sidebar in the Clip Editor"""

    bl_idname = "clip.auto_track_settings"
    bl_label = "Auto Track Settings"

    def execute(self, context):
        area = context.area
        if area.type == 'CLIP_EDITOR':
            area.spaces.active.show_region_ui = True
            self.report({'INFO'}, "Auto Track settings opened")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Clip Editor not active")
            return {'CANCELLED'}




class CLIP_OT_auto_track_start(bpy.types.Operator):
    """Set Motion Model to LocRotScale for UI and active track"""

    bl_idname = "clip.auto_track_start"
    bl_label = "Auto Track Start"

    def execute(self, context):
        try:
            space = context.space_data
            if not (space and space.clip):
                self.report({'ERROR'}, "No movie clip found")
                return {'CANCELLED'}

            props = context.scene.auto_track_settings

            # Calculate margin and minimum distance from the clip's horizontal resolution
            width = space.clip.size[0]
            props.margin = int(width / 200)
            props.min_distance = int(width / 20)

            # Access tracking settings for the active clip
            tracking = space.clip.tracking
            settings = tracking.settings

            # Blender versions may expose the motion model setting under
            # different names; try both possibilities to remain compatible
            if hasattr(settings, "motion_model"):
                settings.motion_model = 'LocRotScale'
            elif hasattr(settings, "default_motion_model"):
                settings.default_motion_model = 'LocRotScale'
            else:
                self.report({'WARNING'}, "Motion model property not found")

            # Update detection and marker defaults so manual "Detect Features"
            # starts with threshold 1 and larger marker sizes. Set both the
            # immediate threshold and the default to cover all Blender
            # versions and UI states.
            if hasattr(settings, "detect_threshold"):
                settings.detect_threshold = 1
            if hasattr(settings, "default_threshold"):
                settings.default_threshold = 1

            if hasattr(settings, "use_default_detect_threshold"):
                settings.use_default_detect_threshold = True

            if hasattr(settings, "default_pattern_size"):
                settings.default_pattern_size = 50
            elif hasattr(settings, "pattern_size"):
                settings.pattern_size = 50

            if hasattr(settings, "use_default_pattern_size"):
                settings.use_default_pattern_size = True

            if hasattr(settings, "default_search_size"):
                settings.default_search_size = 100
            elif hasattr(settings, "search_size"):
                settings.search_size = 100

            if hasattr(settings, "use_default_search_size"):
                settings.use_default_search_size = True

            # Optional: Set motion model for active track
            track = tracking.tracks.active
            if track:
                if hasattr(track, "motion_model"):
                    track.motion_model = 'LocRotScale'
                if hasattr(track, "pattern_size"):
                    track.pattern_size = 50
                if hasattr(track, "search_size"):
                    track.search_size = 100
            else:
                self.report({'WARNING'}, "No active track selected")

            # Force UI refresh
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()

            frame, new_markers = auto_track_wrapper(context)
            if frame is not None:
                if new_markers:
                    self.report(
                        {'INFO'},
                        f"Detect Features run at frame {frame}, {len(new_markers)} markers kept",
                    )
                else:
                    self.report({'INFO'}, f"Detect Features run at frame {frame}, markers removed")
            else:
                self.report({'INFO'}, "Tracking defaults applied")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class CLIP_PT_auto_track_settings_panel(bpy.types.Panel):
    """Panel in the Clip Editor sidebar displaying auto track options"""

    bl_label = "Auto Track Settings"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Auto Track'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.auto_track_settings

        layout.prop(settings, "min_marker_count")
        layout.prop(settings, "min_tracking_length")
        layout.prop(settings, "threshold")
        layout.separator()
        layout.operator(
            CLIP_OT_auto_track_start.bl_idname,
            text="Auto Track Start",
        )


classes = (
    AutoTrackProperties,
    CLIP_OT_auto_track_settings,
    CLIP_OT_auto_track_start,
    CLIP_PT_auto_track_settings_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.auto_track_settings = bpy.props.PointerProperty(
        type=AutoTrackProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.auto_track_settings


if __name__ == "__main__":
    register()
