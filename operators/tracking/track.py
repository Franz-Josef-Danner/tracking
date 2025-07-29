import bpy
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

# Import utility functions via relative path
from ...helpers.prefix_new import PREFIX_NEW
from ...helpers.prefix_track import PREFIX_TRACK
from ...helpers.prefix_good import PREFIX_GOOD
from ...helpers.prefix_testing import PREFIX_TEST
from ...helpers.select_track_tracks import select_track_tracks
from ...helpers.select_new_tracks import select_new_tracks
from ...helpers.select_short_tracks import select_short_tracks
from ...helpers.delete_selected_tracks import delete_selected_tracks
from ...helpers.detection_helpers import (
    detect_features_once,
    find_next_low_marker_frame,
)
from ...helpers.marker_helpers import (
    cleanup_all_tracks,
    ensure_valid_selection,
    select_tracks_by_names,
    select_tracks_by_prefix,
    get_undertracked_markers,
)
from ...helpers.feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    marker_target_conservative,
)
from ...helpers.tracking_variants import (
    track_bidirectional,
    track_forward_only,
)
from ...helpers.tracking_helpers import track_markers_range
from ...helpers.utils import (
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
from ...helpers.set_playhead_to_frame import set_playhead_to_frame
from ..proxy import CLIP_OT_proxy_on, CLIP_OT_proxy_off, CLIP_OT_proxy_build
class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}




class CLIP_OT_track_bidirectional(bpy.types.Operator):
    bl_idname = "clip.track_bidirectional"
    bl_label = "Track"
    bl_description = (
        "Trackt selektierte Marker r\u00fcckw\u00e4rts zum Szenenanfang und danach vorw\u00e4rts"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not any(t.select for t in clip.tracking.tracks):
            self.report({'WARNING'}, "Keine Tracks ausgew\u00e4hlt")
            return {'CANCELLED'}

        scene = context.scene
        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current


        if not bpy.ops.clip.track_markers.poll():
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")
            return {'CANCELLED'}

        scene.frame_start = original_start
        scene.frame_end = current
        bpy.ops.clip.track_markers(backwards=True, sequence=True)

        scene.frame_start = current
        scene.frame_end = original_end
        scene.frame_current = current
        update_frame_display(context)
        bpy.ops.clip.track_markers(backwards=False, sequence=True)

        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_current = current
        update_frame_display(context)


        return {'FINISHED'}


class CLIP_OT_track_partial(bpy.types.Operator):
    bl_idname = "clip.track_partial"
    bl_label = "Track Partial"
    bl_description = (
        "Trackt selektierte Marker r\u00fcckw\u00e4rts bis zum Szenenanfang "
        "und danach vorw\u00e4rts bis zum Szenenende"
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not ensure_valid_selection(clip, scene.frame_current):
            self.report({'WARNING'}, "Keine g\u00fcltigen Marker ausgew\xe4hlt")
            return {'CANCELLED'}

        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current

        print(
            f"[Track Partial] current {current} start {original_start} end {original_end}"
        )

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

class CLIP_OT_track_sequence(bpy.types.Operator):
    bl_idname = "clip.track_sequence"
    bl_label = "Track"
    bl_description = (
        "Verfolgt TRACK_-Marker r\xFCckw\xE4rts in gro\xDFen Bl\xF6cken und danach vorw\xE4rts"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren
        clip.use_proxy = True
        # Prepass und Normalize einschalten
        settings = clip.tracking.settings
        settings.use_default_brute = True
        settings.use_default_normalization = True

        scene = context.scene

        original_start = scene.frame_start
        original_end = scene.frame_end

        current = scene.frame_current

        def count_active_tracks(frame_value):
            count = 0
            for t in clip.tracking.tracks:
                if t.name.startswith(PREFIX_TRACK) or t in PENDING_RENAME:
                    m = t.markers.find_frame(frame_value)
                    if m and not m.mute and m.co.length_squared != 0.0:
                        count += 1
            return count

        clean_pending_tracks(clip)
        for t in clip.tracking.tracks:
            t.select = t.name.startswith(PREFIX_TRACK) or t in PENDING_RENAME

        selected = [t for t in clip.tracking.tracks if t.select]
        selected_names = [t.name for t in selected]

        if not selected:
            return {'CANCELLED'}


        frame = current
        start_frame = original_start
        total_range = frame - start_frame
        if total_range > 1:
            block_size = int(total_range / math.log10(total_range * total_range))
            block_size = max(1, block_size)
        else:
            block_size = 1
        while frame >= start_frame:
            limited_start = max(start_frame, frame - block_size)
            scene.frame_start = limited_start
            scene.frame_end = frame
            bpy.ops.clip.track_markers(backwards=True, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_start)
            if active_count == 0:
                
                break
            frame = limited_start - 1

        frame = current
        end_frame = original_end
        while frame <= end_frame:
            remaining = end_frame - frame
            block_size = max(1, math.ceil(remaining / 4))
            limited_end = min(frame + block_size, end_frame)
            scene.frame_start = frame
            scene.frame_end = limited_end
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_end)
            if active_count == 0:
                break
            frame = limited_end + 1

        scene.frame_start = original_start
        scene.frame_end = original_end


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


class CLIP_OT_track_full(bpy.types.Operator):
    bl_idname = "clip.track_full"
    bl_label = "Track"
    bl_description = (
        "Trackt die Sequenz vorw\u00e4rts und speichert den letzten Frame"
    )

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        global TEST_START_FRAME, TEST_END_FRAME, TEST_SETTINGS, TRACKED_FRAMES, LAST_TRACK_END

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren für das Tracking
        clip.use_proxy = True

        scene = context.scene
        start = scene.frame_current
        TEST_START_FRAME = start

        if bpy.ops.clip.track_markers.poll():
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        else:
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")
            return {'CANCELLED'}

        end_frame = scene.frame_current
        LAST_TRACK_END = end_frame
        TRACKED_FRAMES = end_frame - start
        if TEST_END_FRAME is None or end_frame > TEST_END_FRAME:
            TEST_END_FRAME = end_frame
            settings = clip.tracking.settings
            TEST_SETTINGS = {
                "pattern_size": settings.default_pattern_size,
                "motion_model": settings.default_motion_model,
                "pattern_match": settings.default_pattern_match,
                "channels_active": (
                    settings.use_default_red_channel,
                    settings.use_default_green_channel,
                    settings.use_default_blue_channel,
                ),
            }

        scene.frame_current = start
        update_frame_display(context)
        if not self.silent:
            self.report({'INFO'}, f"Tracking bis Frame {end_frame} abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_test_track_backwards(bpy.types.Operator):
    bl_idname = "clip.test_track_backwards"
    bl_label = "Test Track backwards"
    bl_description = (
        "Trackt alle TEST_-Marker r\u00fcckw\u00e4rts bis zum Szenenanfang"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        select_tracks_by_prefix(clip, PREFIX_TEST)
        if not any(t.select for t in clip.tracking.tracks):
            self.report({'WARNING'}, "Keine TEST_-Tracks gefunden")
            return {'CANCELLED'}

        scene = context.scene
        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current

        if bpy.ops.clip.track_markers.poll():
            scene.frame_start = original_start
            scene.frame_end = current
            clip.use_proxy = True
            bpy.ops.clip.track_markers(backwards=True, sequence=True)
        else:
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")

        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_current = current
        update_frame_display(context)

        for t in clip.tracking.tracks:
            t.select = False

        return {'FINISHED'}


class CLIP_OT_test_track(bpy.types.Operator):
    bl_idname = "clip.test_track"
    bl_label = "Test Track"
    bl_description = (
        "Trackt selektierte Marker vorwärts bis zum Sequenzende"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not any(t.select for t in clip.tracking.tracks):
            self.report({'WARNING'}, "Keine Tracks ausgewählt")
            return {'CANCELLED'}

        scene = context.scene
        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current

        if not bpy.ops.clip.track_markers.poll():
            self.report({'WARNING'}, "Tracking nicht möglich")
            return {'CANCELLED'}

        scene.frame_start = current
        scene.frame_end = original_end
        bpy.ops.clip.track_markers(backwards=False, sequence=True)

        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_current = current
        update_frame_display(context)

        self.report({'INFO'}, "Tracking abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_pattern_up(bpy.types.Operator):
    bl_idname = "clip.pattern_up"
    bl_label = "Pattern+"
    bl_description = "Erh\u00f6ht die Pattern Size um 10 %"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = max(1, int(settings.default_pattern_size * 1.1))
        settings.default_search_size = settings.default_pattern_size * 2
        return {'FINISHED'}


class CLIP_OT_pattern_down(bpy.types.Operator):
    bl_idname = "clip.pattern_down"
    bl_label = "Pattern-"
    bl_description = "Verringert die Pattern Size um 10 %"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = max(1, int(settings.default_pattern_size * 0.9))
        settings.default_search_size = settings.default_pattern_size * 2
        return {'FINISHED'}


class CLIP_OT_motion_cycle(bpy.types.Operator):
    bl_idname = "clip.motion_cycle"
    bl_label = "Motion"
    bl_description = "Wechselt zum n\u00e4chsten Motion Model"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        cycle_motion_model(settings, clip, reset_size=False)
        return {'FINISHED'}


class CLIP_OT_match_cycle(bpy.types.Operator):
    bl_idname = "clip.match_cycle"
    bl_label = "Match"
    bl_description = "Schaltet das Pattern Match um"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        current = settings.default_pattern_match
        if current == 'KEYFRAME':
            settings.default_pattern_match = 'PREV_FRAME'
        else:
            settings.default_pattern_match = 'KEYFRAME'
        return {'FINISHED'}


class CLIP_OT_channel_r_on(bpy.types.Operator):
    bl_idname = "clip.channel_r_on"
    bl_label = "R On"
    bl_description = "Aktiviert den Rotkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_red_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_r_off(bpy.types.Operator):
    bl_idname = "clip.channel_r_off"
    bl_label = "R Off"
    bl_description = "Deaktiviert den Rotkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_red_channel = False
        return {'FINISHED'}


class CLIP_OT_channel_g_on(bpy.types.Operator):
    bl_idname = "clip.channel_g_on"
    bl_label = "G On"
    bl_description = "Aktiviert den Gr\u00fcnkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_green_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_g_off(bpy.types.Operator):
    bl_idname = "clip.channel_g_off"
    bl_label = "G Off"
    bl_description = "Deaktiviert den Gr\u00fcnkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_green_channel = False
        return {'FINISHED'}


class CLIP_OT_channel_b_on(bpy.types.Operator):
    bl_idname = "clip.channel_b_on"
    bl_label = "B On"
    bl_description = "Aktiviert den Blaukanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_blue_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_b_off(bpy.types.Operator):
    bl_idname = "clip.channel_b_off"
    bl_label = "B Off"
    bl_description = "Deaktiviert den Blaukanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_blue_channel = False
        return {'FINISHED'}

operator_classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_track_bidirectional,
    CLIP_OT_track_partial,
    CLIP_OT_track_sequence,
    CLIP_OT_track_full,
    CLIP_OT_test_track_backwards,
    CLIP_OT_test_track,
    CLIP_OT_pattern_up,
    CLIP_OT_pattern_down,
    CLIP_OT_motion_cycle,
    CLIP_OT_match_cycle,
    CLIP_OT_channel_r_on,
    CLIP_OT_channel_r_off,
    CLIP_OT_channel_g_on,
    CLIP_OT_channel_g_off,
    CLIP_OT_channel_b_on,
    CLIP_OT_channel_b_off,
)

