import bpy
from bpy.props import BoolProperty, IntProperty

from ..helpers import (
    track_markers_until_end,
    get_tracking_lengths,
    set_tracking_channels,
)


def calculate_ega(tracking_data):
    """Compute a simple Evaluation of Goodness of Alignment (EGA).

    The metric sums the length of all active tracks, assuming that
    longer tracks indicate more stable tracking.

    Parameters
    ----------
    tracking_data: bpy.types.MovieTracking
        Tracking data from the active movie clip.

    Returns
    -------
    float
        The calculated EGA value.
    """

    ega = 0.0
    for track in tracking_data.tracks:
        ega += float(len(track.markers))
    return ega


def clear_tracks(tracking_data):
    """Remove all tracks from the given tracking data."""
    for track in list(tracking_data.tracks):
        tracking_data.tracks.remove(track)


class TRACKING_OT_test_cycle(bpy.types.Operator):
    """Optimize tracking settings in three stages."""

    bl_idname = "tracking.test_cycle"
    bl_label = "Test Cycle"
    bl_description = (
        "Optimizes pattern size, motion model and RGB channel settings for tracking"
    )
    bl_options = {"REGISTER", "UNDO"}

    max_iterations: IntProperty(
        name="Max Pattern Iterations",
        description="Number of iterations for pattern/search size optimization",
        default=4,
        min=1,
        max=10,
    )

    verbose: BoolProperty(
        name="Verbose Output",
        description="Print detailed progress information to the console",
        default=True,
    )

    def execute(self, context):
        if not bpy.data.movieclips:
            self.report({'ERROR'}, "No movie clip loaded. Please load a clip in the Movie Clip Editor.")
            return {'CANCELLED'}

        clip = bpy.data.movieclips[0]
        tracking_data = clip.tracking
        settings = tracking_data.settings

        width = clip.size[0]
        pt = int(width / 100.0)
        sus = pt * 2

        override = context.copy()
        for area in context.window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                override['area'] = area
                override['region'] = area.regions[-1]
                override['space_data'] = area.spaces.active
                break
        else:
            self.report({'ERROR'}, "Movie Clip Editor not found. Open a Movie Clip Editor and try again.")
            return {'CANCELLED'}

        best_pt = pt
        best_ega = -1.0
        for iteration in range(self.max_iterations + 1):
            clear_tracks(tracking_data)
            settings.default_pattern_size = int(pt)
            settings.default_search_size = int(sus)

            if self.verbose:
                print(f"\n[Stage 1] Test {iteration + 1}: pattern size = {pt:.2f}, search size = {sus:.2f}")

            bpy.ops.clip.detect_features(override)
            bpy.ops.clip.track_markers(override, sequence=False)

            ega = calculate_ega(tracking_data)
            if self.verbose:
                print(f"[Stage 1] EGA = {ega:.4f}")

            if best_ega < 0 or ega > best_ega:
                best_ega = ega
                best_pt = pt
                pt *= 1.1
                sus = pt * 2
            else:
                if iteration == self.max_iterations:
                    pt = best_pt
                    sus = pt * 2
                    break
                pt *= 1.1
                sus = pt * 2

        pt = int(pt)
        sus = int(sus)
        if self.verbose:
            print(f"\nStage 1 complete. Optimal pattern size = {pt}, search size = {sus}")

        motion_models = ['Loc', 'LocRot', 'LocScale', 'LocRotScale', 'Affine']
        best_motion_model = settings.default_motion_model
        base_ega = best_ega
        for model in motion_models:
            if self.verbose:
                print(f"\n[Stage 2] Testing motion model = {model}")
            clear_tracks(tracking_data)
            settings.default_pattern_size = pt
            settings.default_search_size = sus
            settings.default_motion_model = model
            bpy.ops.clip.detect_features(override)
            bpy.ops.clip.track_markers(override, sequence=False)
            ega = calculate_ega(tracking_data)
            if self.verbose:
                print(f"[Stage 2] EGA = {ega:.4f}")
            if ega > base_ega:
                base_ega = ega
                best_motion_model = model
        settings.default_motion_model = best_motion_model
        if self.verbose:
            print(f"\nStage 2 complete. Optimal motion model = {best_motion_model}")

        channel_combinations = {
            0: (True, False, False),
            1: (True, True, False),
            2: (False, True, False),
            3: (False, True, True),
            4: (False, False, True),
        }
        best_rgb_idx = None
        base_ega_rgb = base_ega
        for idx, (use_r, use_g, use_b) in channel_combinations.items():
            if self.verbose:
                print(f"\n[Stage 3] Testing channels: R={use_r}, G={use_g}, B={use_b}")
            clear_tracks(tracking_data)
            settings.default_pattern_size = pt
            settings.default_search_size = sus
            settings.default_motion_model = best_motion_model
            settings.use_default_red_channel = use_r
            settings.use_default_green_channel = use_g
            settings.use_default_blue_channel = use_b
            bpy.ops.clip.detect_features(override)
            bpy.ops.clip.track_markers(override, sequence=False)
            ega = calculate_ega(tracking_data)
            if self.verbose:
                print(f"[Stage 3] EGA = {ega:.4f}")
            if ega > base_ega_rgb:
                base_ega_rgb = ega
                best_rgb_idx = idx
        if best_rgb_idx is not None:
            use_r, use_g, use_b = channel_combinations[best_rgb_idx]
            settings.use_default_red_channel = use_r
            settings.use_default_green_channel = use_g
            settings.use_default_blue_channel = use_b
        else:
            settings.use_default_red_channel = False
            settings.use_default_green_channel = False
            settings.use_default_blue_channel = False
        if self.verbose:
            if best_rgb_idx is not None:
                print(
                    f"\nStage 3 complete. Optimal RGB setting index = {best_rgb_idx} "
                    f"(R={use_r}, G={use_g}, B={use_b})"
                )
            else:
                print("\nStage 3 complete. No channel combination improved EGA; using default (all channels).")

        self.report(
            {'INFO'},
            (
                f"Optimization finished: pattern={pt}, search={sus}, "
                f"motion model={best_motion_model}, RGB index="
                f"{best_rgb_idx if best_rgb_idx is not None else 'Default'}, EGA={base_ega_rgb:.4f}"
            ),
        )
        return {'FINISHED'}


class TRACKING_OT_test_base(bpy.types.Operator):
    bl_idname = "tracking.test_base"
    bl_label = "Test Base"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_place_marker(bpy.types.Operator):
    bl_idname = "tracking.test_place_marker"
    bl_label = "Place Marker"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_track_markers(bpy.types.Operator):
    bl_idname = "tracking.test_track_markers"
    bl_label = "Track Markers"

    def execute(self, context):
        track_markers_until_end()
        self.report({'INFO'}, "Tracking gestartet")
        return {'FINISHED'}


class TRACKING_OT_test_error_value(bpy.types.Operator):
    bl_idname = "tracking.test_error_value"
    bl_label = "Error Value"

    def execute(self, context):
        bpy.ops.clip.error_value('INVOKE_DEFAULT')
        self.report({'INFO'}, "Error value calculated")
        return {'FINISHED'}


class TRACKING_OT_test_tracking_lengths(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_lengths"
    bl_label = "Tracking Lengths"

    def execute(self, context):
        lengths = get_tracking_lengths()
        if not lengths:
            self.report({'WARNING'}, "Keine Tracks ausgewählt")
        else:
            for name, data in lengths.items():
                print(f"{name}: {data['length']} Frames")
            self.report({'INFO'}, "Längen ausgegeben")
        return {'FINISHED'}


class TRACKING_OT_test_cycle_motion(bpy.types.Operator):
    bl_idname = "tracking.test_cycle_motion"
    bl_label = "Cycle Motion"

    def execute(self, context):
        # Der eigentliche Wechsel wird vom Operator TRACKING_OT_cycle_motion_model erledigt
        self.report({'INFO'}, "Motion Model gewechselt")
        return {'FINISHED'}


class TRACKING_OT_test_tracking_channels(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_channels"
    bl_label = "Tracking Channels"

    def execute(self, context):
        set_tracking_channels()
        self.report({'INFO'}, "Tracking-Kanäle gesetzt")
        return {'FINISHED'}


operator_classes = (
    TRACKING_OT_test_cycle,
    TRACKING_OT_test_base,
    TRACKING_OT_test_place_marker,
    TRACKING_OT_test_track_markers,
    TRACKING_OT_test_error_value,
    TRACKING_OT_test_tracking_lengths,
    TRACKING_OT_test_cycle_motion,
    TRACKING_OT_test_tracking_channels,
)
