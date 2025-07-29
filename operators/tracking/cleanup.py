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
class CLIP_OT_delete_selected(bpy.types.Operator):
    bl_idname = "clip.delete_selected"
    bl_label = "Delete"
    bl_description = "Löscht selektierte Tracks"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        has_selection = any(t.select for t in clip.tracking.tracks)
        if not has_selection:
            if not self.silent:
                self.report({'WARNING'}, "Keine Tracks ausgewählt")
            return {'CANCELLED'}

        if delete_selected_tracks():
            clean_pending_tracks(clip)
            if not self.silent:
                self.report({'INFO'}, "Tracks gelöscht")
        else:
            if not self.silent:
                self.report({'WARNING'}, "Löschen nicht möglich")
        return {'FINISHED'}






class CLIP_OT_select_short_tracks(bpy.types.Operator):
    bl_idname = "clip.select_short_tracks"
    bl_label = "Select Short Tracks"
    bl_description = (
        "Selektiert TRACK_-Marker, deren Länge unter 'Frames/Track' liegt"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        min_frames = context.scene.frames_track
        count = select_short_tracks(clip, min_frames)

        if count == 0:
            self.report({'INFO'}, "Keine kurzen TRACK_-Marker gefunden")
        else:
            self.report({'INFO'}, f"{count} TRACK_-Marker ausgewählt")

        return {'FINISHED'}


class CLIP_OT_count_button(bpy.types.Operator):
    bl_idname = "clip.count_button"
    bl_label = "Count"
    bl_description = "Selektiert und zählt TEST_-Tracks"
    silent: BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        prefix = PREFIX_TEST
        for t in clip.tracking.tracks:
            t.select = t.name.startswith(prefix)
        count = sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
        context.scene.nm_count = count

        mframe = context.scene.marker_frame
        mf_base = marker_target_conservative(mframe)
        track_min = mf_base * 0.8
        track_max = mf_base * 1.2

        if track_min <= count <= track_max:
            for t in clip.tracking.tracks:
                if t.name.startswith(prefix):
                    t.name = PREFIX_TRACK + t.name[len(prefix):]
                    t.select = False
            if not self.silent:
                self.report({'INFO'}, f"{count} Tracks in TRACK_ umbenannt")
        else:
            if not self.silent:
                self.report({'INFO'}, f"{count} TEST_-Tracks ausserhalb des Bereichs")
        return {'FINISHED'}


class CLIP_OT_tracking_length(bpy.types.Operator):
    bl_idname = "clip.tracking_length"
    bl_label = "Tracking Length"
    bl_description = (
        "Löscht TRACK_-Marker, deren Länge unter 'Frames/Track' liegt"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        min_frames = context.scene.frames_track
        undertracked = get_undertracked_markers(clip, min_frames=min_frames)

        if not undertracked:
            self.report({'INFO'}, "Alle TRACK_-Marker erreichen die gewünschte Länge")
            return {'FINISHED'}

        names = [name for name, _ in undertracked]
        select_tracks_by_names(clip, names)

        if delete_selected_tracks():
            self.report({'INFO'}, f"{len(names)} TRACK_-Marker gelöscht")
        else:
            self.report({'WARNING'}, "Löschen nicht möglich")

        remaining = [t for t in clip.tracking.tracks if t.name.startswith(PREFIX_TRACK)]
        select_tracks_by_names(clip, [t.name for t in remaining])
        for t in remaining:
            t.name = PREFIX_GOOD + t.name[len(PREFIX_TRACK):]

        for t in clip.tracking.tracks:
            t.select = False

        return {'FINISHED'}


class CLIP_OT_playhead_to_frame(bpy.types.Operator):
    bl_idname = "clip.playhead_to_frame"
    bl_label = "Playhead to Frame"
    bl_description = (
        "Springt zum ersten Frame, in dem weniger GOOD_-Marker aktiv sind als 'Marker/Frame' vorgibt"
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        frame, _ = find_next_low_marker_frame(
            scene,
            clip,
            scene.marker_frame,
        )
        if frame is not None:
            set_playhead_to_frame(scene, frame)
        return {'FINISHED'}


class CLIP_OT_low_marker_frame(bpy.types.Operator):
    bl_idname = "clip.low_marker_frame"
    bl_label = "Low Marker Frame"
    bl_description = (
        "Springt zum ersten Frame mit weniger Markern als 'Marker/Frame'"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        scene = context.scene
        threshold = scene.marker_frame
        frame, count = find_next_low_marker_frame(
            scene,
            clip,
            threshold,
        )
        if frame is not None:
            set_playhead_to_frame(scene, frame)
            self.report(
                {'INFO'},
                f"Frame {frame} hat weniger als {threshold} Marker",
            )
        else:
            self.report({'INFO'}, "Kein Frame mit weniger Markern gefunden")

        return {'FINISHED'}


class CLIP_OT_select_active_tracks(bpy.types.Operator):
    bl_idname = "clip.select_active_tracks"
    bl_label = "Select TRACK"
    bl_description = (
        "Selektiert alle TRACK_-Marker ungeachtet ihres Status"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        select_track_tracks(clip)

        frame = context.scene.frame_current

        for track in clip.tracking.tracks:
            if track.select:
                marker = track.markers.find_frame(frame, exact=True)
                if marker is None or marker.mute:
                    track.select = False

        count = sum(1 for t in clip.tracking.tracks if t.select)

        self.report({'INFO'}, f"{count} TRACK_-Marker ausgewählt")
        return {'FINISHED'}

class CLIP_OT_select_new_tracks(bpy.types.Operator):
    bl_idname = "clip.select_new_tracks"
    bl_label = "Select NEW"
    bl_description = "Selektiert alle NEW_-Marker"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        select_new_tracks(clip)
        count = sum(1 for t in clip.tracking.tracks if t.select)
        self.report({'INFO'}, f"{count} NEW_-Marker ausgewählt")
        return {'FINISHED'}


class CLIP_OT_select_test_tracks(bpy.types.Operator):
    bl_idname = "clip.select_test_tracks"
    bl_label = "Select TEST"
    bl_description = "Selektiert alle TEST_-Marker"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        select_tracks_by_prefix(clip, PREFIX_TEST)
        count = sum(1 for t in clip.tracking.tracks if t.select)
        self.report({'INFO'}, f"{count} TEST_-Marker ausgewählt")
        return {'FINISHED'}


class CLIP_OT_marker_position(bpy.types.Operator):
    bl_idname = "clip.marker_position"
    bl_label = "Marker Position"
    bl_description = (
        "Gibt die Pixelposition der Marker in selektierten Tracks im aktuellen Frame aus"
    )

    def get_selected_marker_positions_in_pixels(self, scene):
        frame = scene.frame_current
        clip = scene.active_clip

        if clip is None:
            raise RuntimeError("Kein aktiver Clip im Clip-Editor.")

        width, height = clip.size
        result = []

        for track in clip.tracking.tracks:
            if not track.select:
                continue

            marker = track.markers.find_frame(frame, exact=True)
            if marker is None or marker.mute:
                continue

            x_px = marker.co[0] * width
            y_px = marker.co[1] * height

            result.append(
                {
                    "track_name": track.name,
                    "frame": frame,
                    "x_px": x_px,
                    "y_px": y_px,
                }
            )

        return result

    def execute(self, context):
        try:
            markers = self.get_selected_marker_positions_in_pixels(context.scene)
        except RuntimeError as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}

        for m in markers:
            print(
                f"[{m['track_name']}] Frame {m['frame']}: "
                f"X={m['x_px']:.1f}px, Y={m['y_px']:.1f}px"
            )

        return {'FINISHED'}


class CLIP_OT_good_marker_position(bpy.types.Operator):
    bl_idname = "clip.good_marker_position"
    bl_label = "GOOD Marker Position"
    bl_description = (
        "Gibt die Pixelposition aller sichtbaren GOOD_-Marker im aktuellen Frame aus"
    )

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        clip = scene.active_clip

        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip-Editor gefunden")
            return {'CANCELLED'}

        width, height = clip.size
        good_markers_px = []

        for track in clip.tracking.tracks:
            if not track.name.startswith(PREFIX_GOOD):
                continue

            marker = track.markers.find_frame(frame, exact=True)
            if marker is None or marker.mute:
                continue

            nx, ny = marker.co
            px, py = nx * width, ny * height

            good_markers_px.append({
                "track_name": track.name,
                "frame": frame,
                "x_px": px,
                "y_px": py,
            })

        for m in good_markers_px:
            print(
                f"[{m['track_name']} @ frame {m['frame']}] -> X: {m['x_px']:.1f} px, Y: {m['y_px']:.1f} px"
            )

        return {'FINISHED'}














operator_classes = (
    CLIP_OT_delete_selected,
    CLIP_OT_select_short_tracks,
    CLIP_OT_count_button,
    CLIP_OT_tracking_length,
    CLIP_OT_playhead_to_frame,
    CLIP_OT_low_marker_frame,
    CLIP_OT_select_active_tracks,
    CLIP_OT_select_new_tracks,
    CLIP_OT_select_test_tracks,
    CLIP_OT_marker_position,
    CLIP_OT_good_marker_position,
)

