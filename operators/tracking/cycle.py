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
from tracking_tools.helpers.proxy_helpers import enable_proxy
from tracking_tools.helpers.set_playhead_to_frame import set_playhead_to_frame
from ..proxy import CLIP_OT_proxy_on, CLIP_OT_proxy_off, CLIP_OT_proxy_build
from .cleanup import cleanup_short_tracks
class CLIP_OT_track_nr1(bpy.types.Operator):
    bl_idname = "clip.track_nr1"
    bl_label = "Track Nr. 1"
    bl_description = "Temporär deaktivierter Tracking-Button"

    def execute(self, context):
        self.report({'INFO'}, "Tracking Started")
        print("📢 Tracking Started")
        return {'FINISHED'}


class CLIP_OT_track_nr2(bpy.types.Operator):
    bl_idname = "clip.track_nr2"
    bl_label = "Track Nr. 2"
    bl_description = (
        "1. Suche Frame mit zu wenig Markern\n"
        "2. Setze Playhead\n"
        "3. F\u00fchre Feature Detection durch\n"
        "4. Wende Threshold-Tests an\n"
        "5. Track bidirektional\n"
        "6. Entferne schlechte Tracks\n"
        "7. Wiederhole Zyklus bis Ende"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        def handle_frame(frame_number):
            global TRACK_ATTEMPTS
            attempts = TRACK_ATTEMPTS.get(frame_number, 0)
            if attempts > 0:
                if bpy.ops.clip.marker_frame_plus.poll():
                    bpy.ops.clip.marker_frame_plus()
            else:
                if bpy.ops.clip.marker_frame_minus.poll():
                    bpy.ops.clip.marker_frame_minus()
            attempts += 1
            TRACK_ATTEMPTS[frame_number] = attempts
            if attempts > 10:
                self.report(
                    {'ERROR'},
                    f"Zu viele Tracking-Versuche in Frame {frame_number}",
                )
                return False
            return True

        if bpy.ops.clip.setup_defaults.poll():
            bpy.ops.clip.setup_defaults()

        threshold = scene.marker_frame
        frame = jump_to_frame_with_few_markers(
            clip,
            min_marker_count=threshold,
            start_frame=scene.frame_start,
            end_frame=scene.frame_end,
        )
        if frame is not None:
            update_frame_display(context)
            if not handle_frame(frame):
                return {'CANCELLED'}

        cycles = 0
        while True:
            if bpy.ops.clip.test_pattern.poll():
                bpy.ops.clip.test_pattern()
            if bpy.ops.clip.test_motion.poll():
                bpy.ops.clip.test_motion()
            if bpy.ops.clip.test_channel.poll():
                bpy.ops.clip.test_channel()
            if bpy.ops.clip.cycle_detect.poll():
                bpy.ops.clip.cycle_detect()
            if bpy.ops.clip.track_partial.poll():
                track_forward_only(scene.frame_start, scene.frame_end)
            if bpy.ops.clip.cleanup.poll():
                bpy.ops.clip.cleanup()
                if bpy.ops.clip.setup_defaults.poll():
                    bpy.ops.clip.setup_defaults()

            cycles += 1
            current = scene.frame_current
            frame = jump_to_frame_with_few_markers(
                clip,
                min_marker_count=threshold,
                start_frame=current + 1,
                end_frame=scene.frame_end,
            )
            if frame is not None and frame != current and cycles < 100:
                update_frame_display(context)
                if not handle_frame(frame):
                    return {'CANCELLED'}
                continue
            if cycles >= 100:
                self.report({'WARNING'}, "Abbruch nach 100 Durchl\u00e4ufen")
            break

        self.report({'INFO'}, f"{cycles} Durchl\u00e4ufe ausgef\u00fchrt")
        return {'FINISHED'}




class CLIP_OT_all_cycle(bpy.types.Operator):
    bl_idname = "clip.all_cycle"
    bl_label = "All Cycle"
    bl_description = (
        "Startet einen kombinierten Tracking-Zyklus ohne Proxy-Bau, der mit Esc abgebrochen werden kann"
    )

    _timer = None
    _state = "DETECT"
    _detect_attempts = 0

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.cancel(context)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return self.cancel(context)

        if self._state == 'DETECT':
            bpy.ops.clip.all_detect()
            bpy.ops.clip.distance_button()
            delete_selected_tracks()
            clean_pending_tracks(clip)

            count = len(PENDING_RENAME)
            mframe = context.scene.marker_frame
            mf_base = marker_target_aggressive(mframe)
            track_min = mf_base * 0.8
            track_max = mf_base * 1.2

            if track_min <= count <= track_max:
                for t in PENDING_RENAME:
                    t.select = True
                self._detect_attempts = 0
                self._state = 'TRACK'
            else:
                for t in PENDING_RENAME:
                    t.select = True
                delete_selected_tracks()
                clean_pending_tracks(clip)
                self._detect_attempts += 1
                if self._detect_attempts >= 20:
                    self.report({'WARNING'}, "Maximale Wiederholungen erreicht")
                    return self.cancel(context)

        elif self._state == 'TRACK':
            bpy.ops.clip.track_sequence()
            self._state = 'CLEAN'

        elif self._state == 'CLEAN':
            bpy.ops.clip.tracking_length()
            self._state = 'JUMP'

        elif self._state == 'JUMP':
            frame = jump_to_frame_with_few_markers(
                context.space_data.clip,
                min_marker_count=context.scene.marker_frame,
                start_frame=context.scene.frame_start,
                end_frame=context.scene.frame_end,
            )
            if frame is None:
                return self.cancel(context)
            update_frame_display(context)
            self._state = 'DETECT'

        return {'PASS_THROUGH'}

    def execute(self, context):
        self._state = 'DETECT'
        self._detect_attempts = 0
        wm = context.window_manager
        self._timer = add_timer(wm, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        clip = context.space_data.clip
        if clip:
            rename_pending_tracks(clip)
        return {'CANCELLED'}


class CLIP_OT_step_track(bpy.types.Operator):
    bl_idname = "clip.step_track"
    bl_label = "Step Track"
    bl_description = (
        "Führt Detect, Name Track, Select TRACK und Track Partial aus "
        "und springt anschließend um 'Frames/Track' vor"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        scene = context.scene
        step = scene.frames_track
        end_frame = scene.frame_end

        while scene.frame_current <= end_frame:
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()
            if bpy.ops.clip.prefix_track.poll():
                bpy.ops.clip.prefix_track()
            if bpy.ops.clip.select_active_tracks.poll():
                bpy.ops.clip.select_active_tracks()
            if bpy.ops.clip.track_partial.poll():
                bpy.ops.clip.track_partial()

            # Nach dem Tracken erneut Marker erkennen
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()

            next_frame = scene.frame_current + step
            if next_frame > end_frame:
                break
            scene.frame_current = next_frame
            update_frame_display(context)

        return {'FINISHED'}



operator_classes = (
    CLIP_OT_track_nr1,
    CLIP_OT_track_nr2,
    CLIP_OT_all_cycle,
    CLIP_OT_step_track,
)

