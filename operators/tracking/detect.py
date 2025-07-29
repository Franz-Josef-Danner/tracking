import bpy
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

# Import utility functions via relative path
from tracking_tools.helpers.prefix_new import PREFIX_NEW
from tracking_tools.helpers.prefix_track import PREFIX_TRACK
from tracking_tools.helpers.prefix_good import PREFIX_GOOD
from tracking_tools.helpers.prefix_testing import PREFIX_TEST
from tracking_tools.helpers.select_track_tracks import select_track_tracks
from tracking_tools.helpers.select_new_tracks import select_new_tracks
from tracking_tools.helpers.select_short_tracks import select_short_tracks
from tracking_tools.helpers.delete_selected_tracks import delete_selected_tracks
from tracking_tools.helpers.detection_helpers import (
    detect_features_once,
    find_next_low_marker_frame,
)
from tracking_tools.helpers.marker_helpers import (
    cleanup_all_tracks,
    ensure_valid_selection,
    select_tracks_by_names,
    select_tracks_by_prefix,
    get_undertracked_markers,
)
from tracking_tools.helpers.feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    marker_target_conservative,
)
from tracking_tools.helpers.tracking_variants import (
    track_bidirectional,
    track_forward_only,
)
from tracking_tools.helpers.tracking_helpers import track_markers_range
from tracking_tools.helpers.utils import (
    add_timer,
    jump_to_frame_with_few_markers,
    compute_detection_params,
    pattern_base,
    clamp_pattern_size,
    detect_new_tracks,
    remove_close_tracks,
    add_pending_tracks,
    clean_pending_tracks,
    rename_pending_tracks,
    update_frame_display,
    cycle_motion_model,
)
from tracking_tools.helpers.set_playhead_to_frame import set_playhead_to_frame
from ..proxy import CLIP_OT_proxy_on, CLIP_OT_proxy_off, CLIP_OT_proxy_build
class CLIP_OT_detect_button(bpy.types.Operator):
    bl_idname = "clip.detect_button"
    bl_label = "Test Detect"
    bl_description = "Erkennt Features mit dynamischen Parametern"

    def execute(self, context):
        space = context.space_data
        clip = space.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = False

        global LAST_DETECT_COUNT

        width, _ = clip.size
        if width == 0:
            self.report({'WARNING'}, "Ung\u00fcltige Clipgr\u00f6\u00dfe")
            return {'CANCELLED'}

        mframe = context.scene.marker_frame
        mf_base = marker_target_conservative(mframe)

        threshold_value = context.scene.tracker_threshold

        margin_base, min_distance_base = calculate_base_values(width)
        print(
            f"[BASE DEBUG] width={width}, margin_base={margin_base}, min_distance_base={min_distance_base}"
        )
        detection_threshold, margin, min_distance = compute_detection_params(
            threshold_value, margin_base, min_distance_base
        )


        active = None
        if hasattr(space, "tracking"):
            active = space.tracking.active_track
        if active:
            base = pattern_base(clip)
            active.pattern_size = clamp_pattern_size(base, clip)
            active.search_size = active.pattern_size * 2

        mf_min = mf_base * 0.9
        mf_max = mf_base * 1.1
        attempt = 0
        new_markers = 0

        while True:
            names_before = {t.name for t in clip.tracking.tracks}
            print(
                f"[Detect Features] threshold {detection_threshold:.8f}, "
                f"margin {margin}, min_distance {min_distance}"
            )
            bpy.ops.clip.detect_features(
                threshold=detection_threshold,
                min_distance=min_distance,
                margin=margin,
            )
            print(
                f"[Detect Features] finished threshold {detection_threshold:.8f}, "
                f"margin {margin}, min_distance {min_distance}"
            )
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            for track in clip.tracking.tracks:
                track.select = False
            new_markers = len(new_tracks)
            if mf_min <= new_markers <= mf_max or attempt >= 10:
                break
            # neu erkannte Marker wie beim Delete-Operator entfernen
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            if new_tracks:
                if delete_selected_tracks():
                    clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False
            threshold_value = threshold_value * ((new_markers + 0.1) / mf_base)
            print(f"[Detect Features] updated threshold = {threshold_value:.8f}")
            # adjust detection threshold dynamically
            detection_threshold, margin, min_distance = compute_detection_params(
                threshold_value, margin_base, min_distance_base
            )
            attempt += 1

        settings = clip.tracking.settings
        if (
            LAST_DETECT_COUNT is not None
            and new_markers == LAST_DETECT_COUNT
            and new_markers > 0
            and detection_threshold <= MIN_THRESHOLD
        ):
            settings.default_pattern_size = int(settings.default_pattern_size * 0.9)
            settings.default_pattern_size = clamp_pattern_size(
                settings.default_pattern_size, clip
            )
            settings.default_search_size = settings.default_pattern_size * 2
        LAST_DETECT_COUNT = new_markers
        context.scene.threshold_value = threshold_value
        context.scene.tracker_threshold = threshold_value
        context.scene.nm_count = new_markers
        # Keep newly detected tracks selected
        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        add_pending_tracks(new_tracks)
        self.report({'INFO'}, f"{new_markers} Marker nach {attempt+1} Durchläufen")
        return {'FINISHED'}




class CLIP_OT_distance_button(bpy.types.Operator):
    bl_idname = "clip.distance_button"
    bl_label = "Distance"
    bl_description = (
        "Markiert neu erkannte Tracks, die zu nah an GOOD_ Tracks liegen, "
        "und deselektiert alle anderen"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        frame = context.scene.frame_current
        width, height = clip.size
        min_distance_px = int(width * 0.002)

        clean_pending_tracks(clip)

        # Alle Tracks zunächst deselektieren
        for t in clip.tracking.tracks:
            t.select = False

        new_tracks = list(PENDING_RENAME)
        good_tracks = [t for t in clip.tracking.tracks if t.name.startswith(PREFIX_GOOD)]
        marked = 0
        for nt in new_tracks:
            nm = nt.markers.find_frame(frame)
            if not nm:
                continue
            nx = nm.co[0] * width
            ny = nm.co[1] * height
            for gt in good_tracks:
                gm = gt.markers.find_frame(frame)
                if not gm:
                    continue
                gx = gm.co[0] * width
                gy = gm.co[1] * height
                dist = math.hypot(nx - gx, ny - gy)
                if dist < min_distance_px:
                    nt.select = True
                    marked += 1
                    break
        self.report({'INFO'}, f"{marked} Tracks markiert")
        return {'FINISHED'}


class CLIP_OT_defaults_detect(bpy.types.Operator):
    bl_idname = "clip.defaults_detect"
    bl_label = "Test Detect"
    bl_description = (
        "Wiederholt Detect und Count, bis genug Marker vorhanden sind"
    )

    def execute(self, context):
        return _Test_detect(self, context, use_defaults=False)


class CLIP_OT_motion_detect(bpy.types.Operator):
    bl_idname = "clip.motion_detect"
    bl_label = "Test Detect MM"
    bl_description = (
        "F\u00fchrt Test Detect mit jedem Motion Model aus und speichert das beste Ergebnis"
    )

    def execute(self, context):
        global TEST_END_FRAME, TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        original_model = settings.default_motion_model

        best_end = TEST_END_FRAME
        best_model = original_model

        # Apply stored defaults once
        settings.default_pattern_size = TEST_SETTINGS.get(
            "pattern_size", settings.default_pattern_size
        )
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_pattern_match = TEST_SETTINGS.get(
            "pattern_match", settings.default_pattern_match
        )
        r, g, b = TEST_SETTINGS.get("channels_active", (True, True, True))
        settings.use_default_red_channel = r
        settings.use_default_green_channel = g
        settings.use_default_blue_channel = b

        for model in MOTION_MODELS:
            settings.default_motion_model = model
            end_frame = _Test_detect_mm(self, context)
            if end_frame is None:
                continue
            self.report(
                {'INFO'},
                f"Run end_frame={end_frame}, pattern_size={settings.default_pattern_size}, "
                f"motion_model={model}, "
                f"channels=({settings.use_default_red_channel}, {settings.use_default_green_channel}, {settings.use_default_blue_channel})",
            )
            if best_end is None or end_frame > best_end:
                best_end = end_frame
                best_model = model

        settings.default_motion_model = best_model
        TEST_END_FRAME = best_end
        TEST_SETTINGS["motion_model"] = best_model

        self.report(
            {'INFO'},
            f"Test Detect MM best_end_frame={TEST_END_FRAME}, "
            f"pattern_size={TEST_SETTINGS.get('pattern_size')}, "
            f"motion_model={best_model}, "
            f"channels={TEST_SETTINGS.get('channels_active')}"
        )

        self.report({'INFO'}, "Test Detect MM abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_channel_detect(bpy.types.Operator):
    bl_idname = "clip.channel_detect"
    bl_label = "Test Detect CH"
    bl_description = (
        "F\u00fchrt Test Detect mit verschiedenen Farbkan\u00e4len aus und speichert das beste Ergebnis"
    )

    def execute(self, context):
        global TEST_END_FRAME, TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings

        best_end = TEST_END_FRAME
        best_channels = (
            settings.use_default_red_channel,
            settings.use_default_green_channel,
            settings.use_default_blue_channel,
        )

        # Apply stored defaults once
        settings.default_pattern_size = TEST_SETTINGS.get(
            "pattern_size", settings.default_pattern_size
        )
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_motion_model = TEST_SETTINGS.get(
            "motion_model", settings.default_motion_model
        )
        settings.default_pattern_match = TEST_SETTINGS.get(
            "pattern_match", settings.default_pattern_match
        )

        for channels in CHANNEL_COMBOS:
            (
                settings.use_default_red_channel,
                settings.use_default_green_channel,
                settings.use_default_blue_channel,
            ) = channels
            end_frame = _Test_detect_mm(self, context)
            if end_frame is None:
                continue
            self.report(
                {'INFO'},
                f"Run end_frame={end_frame}, pattern_size={settings.default_pattern_size}, "
                f"motion_model={settings.default_motion_model}, "
                f"channels={channels}",
            )
            if best_end is None or end_frame > best_end:
                best_end = end_frame
                best_channels = channels

        (
            settings.use_default_red_channel,
            settings.use_default_green_channel,
            settings.use_default_blue_channel,
        ) = best_channels
        TEST_END_FRAME = best_end
        TEST_SETTINGS["channels_active"] = best_channels

        self.report(
            {'INFO'},
            f"Test Detect CH best_end_frame={TEST_END_FRAME}, "
            f"pattern_size={TEST_SETTINGS.get('pattern_size')}, "
            f"motion_model={TEST_SETTINGS.get('motion_model')}, "
            f"channels={best_channels}"
        )

        self.report({'INFO'}, "Test Detect CH abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_apply_settings(bpy.types.Operator):
    bl_idname = "clip.apply_detect_settings"
    bl_label = "Test Detect Apply"
    bl_description = (
        "Setzt gespeicherte Test Detect Werte f\u00fcr Pattern, Motion Model und RGB"
        " Kan\u00e4le"
    )

    def execute(self, context):
        global TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings

        pattern_size = TEST_SETTINGS.get("pattern_size")
        if pattern_size is not None:
            settings.default_pattern_size = pattern_size
            settings.default_search_size = pattern_size * 2

        # Extras: Mindestkorrelation und Margin
        settings.default_correlation_min = 0.9
        settings.default_margin = settings.default_pattern_size * 2

        motion_model = TEST_SETTINGS.get("motion_model")
        if motion_model is not None:
            settings.default_motion_model = motion_model

        channels = TEST_SETTINGS.get("channels_active")
        if channels:
            r, g, b = channels
            settings.use_default_red_channel = r
            settings.use_default_green_channel = g
            settings.use_default_blue_channel = b

        self.report({'INFO'}, "Gespeicherte Test Detect Werte gesetzt")
        return {'FINISHED'}


class CLIP_OT_all_detect(bpy.types.Operator):
    bl_idname = "clip.all_detect"
    bl_label = "Detect"
    bl_description = (
        "F\u00fchrt den Detect-Schritt aus All Cycle einzeln aus"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        width, _ = clip.size
        if width == 0:
            self.report({'WARNING'}, "Ung\u00fcltige Clipgr\u00f6\u00dfe")
            return {'CANCELLED'}

        margin_base, min_distance_base = calculate_base_values(width)
        print(
            f"[BASE DEBUG] width={width}, margin_base={margin_base}, min_distance_base={min_distance_base}"
        )

        mfp = marker_target_aggressive(context.scene.marker_frame)
        mfp_min = mfp * 0.9
        mfp_max = mfp * 1.1

        threshold_value = context.scene.tracker_threshold
        detection_threshold, margin, min_distance = compute_detection_params(
            threshold_value, margin_base, min_distance_base
        )


        attempt = 0
        new_markers = 0
        while True:
            names_before = {t.name for t in clip.tracking.tracks}
            print(
                f"[Detect Features] threshold {detection_threshold:.8f}, "
                f"margin {margin}, min_distance {min_distance}"
            )
            bpy.ops.clip.detect_features(
                threshold=detection_threshold,
                min_distance=min_distance,
                margin=margin,
            )
            print(
                f"[Detect Features] finished threshold {detection_threshold:.8f}, "
                f"margin {margin}, min_distance {min_distance}"
            )
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]

            new_markers = len(new_tracks)

            # Select new tracks for position logging
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True

            # Output marker positions before validation
            if bpy.ops.clip.marker_position.poll():
                bpy.ops.clip.marker_position()
            if bpy.ops.clip.good_marker_position.poll():
                bpy.ops.clip.good_marker_position()

            # Compare coordinates with GOOD_ markers and mark nearby tracks
            frame = context.scene.frame_current
            width, height = clip.size
            # Use the computed min_distance as pixel radius
            distance_px = min_distance
            close_tracks = []
            good_positions = []
            for gt in clip.tracking.tracks:
                if not gt.name.startswith(PREFIX_GOOD):
                    continue
                gm = gt.markers.find_frame(frame, exact=True)
                if gm and not gm.mute:
                    good_positions.append((gm.co[0] * width, gm.co[1] * height))
            for nt in new_tracks:
                nm = nt.markers.find_frame(frame, exact=True)
                if nm and not nm.mute:
                    nx = nm.co[0] * width
                    ny = nm.co[1] * height
                    for gx, gy in good_positions:
                        if math.hypot(nx - gx, ny - gy) < distance_px:
                            close_tracks.append(nt)
                            break

            # Delete tracks that are too close to GOOD_ markers
            for track in clip.tracking.tracks:
                track.select = False
            for t in close_tracks:
                t.select = True
            if close_tracks:
                if delete_selected_tracks():
                    clean_pending_tracks(clip)

            # Recompute new tracks after deletion
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]
            new_markers = len(new_tracks)

            # Clear selection again
            for track in clip.tracking.tracks:
                track.select = False

            if mfp_min <= new_markers <= mfp_max or attempt >= 10:
                break

            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            if new_tracks:
                if delete_selected_tracks():
                    clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False

            threshold_value = threshold_value * ((new_markers + 0.1) / mfp)
            print(f"[Detect Features] updated threshold = {threshold_value:.8f}")
            detection_threshold, margin, min_distance = compute_detection_params(
                threshold_value, margin_base, min_distance_base
            )
            attempt += 1

        context.scene.threshold_value = threshold_value
        context.scene.tracker_threshold = threshold_value
        context.scene.nm_count = new_markers

        # Keep newly detected tracks selected
        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        add_pending_tracks(new_tracks)

        return {'FINISHED'}


class CLIP_OT_cycle_detect(bpy.types.Operator):
    bl_idname = "clip.cycle_detect"
    bl_label = "Cycle Detect"
    bl_description = (
        "Wiederholt Detect Features bis zur Zielanzahl und pr\u00fcft den Abstand zu GOOD_-, TRACK_- und NEW_-Markern"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        clip.use_proxy = False

        width, _ = clip.size

        margin_base, min_distance_base = calculate_base_values(width)
        print(f"[BASE DEBUG] width={width}, margin_base={margin_base}, min_distance_base={min_distance_base}")

        target = marker_target_aggressive(context.scene.marker_frame)
        target_min = target * 0.9
        target_max = target * 1.1

        threshold_value = context.scene.tracker_threshold
        detection_threshold, margin, min_distance = compute_detection_params(
            threshold_value, margin_base, min_distance_base
        )

        attempt = 0
        new_tracks = []
        while True:
            new_tracks, before = detect_new_tracks(
                clip, detection_threshold, min_distance, margin
            )
            new_tracks = remove_close_tracks(
                clip, new_tracks, min_distance, before
            )
            count = len(new_tracks)

            for track in clip.tracking.tracks:
                track.select = False

            if target_min <= count <= target_max or attempt >= 10:
                break

            for t in new_tracks:
                t.select = True
            if new_tracks:
                if delete_selected_tracks():
                    clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False

            threshold_value = threshold_value * ((count + 0.1) / target)
            print(f"[Detect Features] updated threshold = {threshold_value:.8f}")
            print(
                f"[BASE DEBUG] width={width}, margin_base={margin_base}, min_distance_base={min_distance_base}"
            )
            detection_threshold, margin, min_distance = compute_detection_params(
                threshold_value, margin_base, min_distance_base
            )
            attempt += 1

        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        if new_tracks and bpy.ops.clip.prefix_new.poll():
            bpy.ops.clip.prefix_new(silent=True)
        add_pending_tracks(new_tracks)

        context.scene.threshold_value = threshold_value
        context.scene.tracker_threshold = threshold_value

        return {'FINISHED'}

def _Test_detect(self, context, use_defaults=True):
    """Run the Test detect cycle optionally using default settings."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return {'CANCELLED'}

    mf_base = marker_target_conservative(context.scene.marker_frame)
    mf_min = mf_base * 0.9
    mf_max = mf_base * 1.1

    if use_defaults:
        bpy.ops.clip.setup_defaults(silent=True)


    # Begin Test detect cycle
    prev_best = TEST_END_FRAME
    last_end = None
    while True:
        for cycle in range(4):
            attempt = 0
            while True:
                # run detection for each attempt
                bpy.ops.clip.detect_button()
                count = sum(
                    1 for t in clip.tracking.tracks if t.name.startswith(PREFIX_TEST)
                )
                context.scene.nm_count = count
                if mf_min <= count <= mf_max or attempt >= 10:
                    break
                for t in clip.tracking.tracks:
                    t.select = t.name.startswith(PREFIX_TEST)
                delete_selected_tracks()
                for t in clip.tracking.tracks:
                    t.select = False
                attempt += 1

            if attempt >= 10 and not (mf_min <= count <= mf_max):
                self.report({'WARNING'}, "Maximale Wiederholungen erreicht")
                return {'CANCELLED'}

            select_tracks_by_prefix(clip, PREFIX_TEST)
            if bpy.ops.clip.track_full.poll():
                bpy.ops.clip.track_full(silent=True)
                last_end = LAST_TRACK_END
                s = clip.tracking.settings
                self.report(
                    {'INFO'},
                    f"Run end_frame={last_end}, pattern_size={s.default_pattern_size}, "
                    f"motion_model={s.default_motion_model}, "
                    f"channels=({s.use_default_red_channel}, {s.use_default_green_channel}, {s.use_default_blue_channel})",
                )
            else:
                self.report({'WARNING'}, "Tracking nicht möglich")

            select_tracks_by_prefix(clip, PREFIX_TEST)
            delete_selected_tracks()
            if bpy.ops.clip.pattern_up.poll():
                bpy.ops.clip.pattern_up()
            for t in clip.tracking.tracks:
                t.select = False

        if prev_best is None or (last_end is not None and last_end > prev_best):
            prev_best = last_end
        elif last_end is not None and last_end < prev_best:
            break

    from_settings = TEST_SETTINGS or {}
    self.report(
        {'INFO'},
        f"Test Detect best_end_frame={TEST_END_FRAME}, "
        f"pattern_size={from_settings.get('pattern_size')}, "
        f"motion_model={from_settings.get('motion_model')}, "
        f"channels={from_settings.get('channels_active')}"
    )
    self.report({'INFO'}, f"{count} Marker gefunden")
    return {'FINISHED'}


def _Test_detect_mm(self, context):
    """Run a shortened Test detect cycle for motion-model tests."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return None

    if not TEST_SETTINGS:
        self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
        return None

    scene = context.scene

    start = TEST_START_FRAME if TEST_START_FRAME is not None else scene.frame_current

    best_end = None
    for cycle in range(4):
        scene.frame_current = start
        update_frame_display(context)
        # run detect for each motion model cycle
        bpy.ops.clip.detect_button()

        select_tracks_by_prefix(clip, PREFIX_TEST)
        if bpy.ops.clip.track_markers.poll():
            # Proxy aktivieren für das Tracking
            clip.use_proxy = True
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            end_frame = scene.frame_current
            if best_end is None or end_frame > best_end:
                best_end = end_frame
        else:
            self.report({'WARNING'}, "Tracking nicht möglich")
            break

        select_tracks_by_prefix(clip, PREFIX_TEST)
        delete_selected_tracks()
        for t in clip.tracking.tracks:
            t.select = False

    scene.frame_current = start
    update_frame_display(context)
    return best_end



operator_classes = (
    CLIP_OT_detect_button,
    CLIP_OT_distance_button,
    CLIP_OT_defaults_detect,
    CLIP_OT_motion_detect,
    CLIP_OT_channel_detect,
    CLIP_OT_apply_settings,
    CLIP_OT_all_detect,
    CLIP_OT_cycle_detect,
)

