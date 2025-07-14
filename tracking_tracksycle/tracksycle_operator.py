"""Main operator implementing the tracking cycle."""

import bpy
from bpy.props import IntProperty, FloatProperty

from .tracker_logger import TrackerLogger
from .distance_remove import remove_nearby_tracks
from .track import track_bidirectional
from .track_length import remove_short_tracks
from .find_frame_with_few_tracking_markers import find_sparse_frame
from .set_playhead import set_playhead
from .motion_model import motion_model_cycle


class KAISERLICH_OT_auto_track_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich.auto_track_cycle"
    bl_label = "Auto Track Cycle"
    bl_options = {'REGISTER', 'UNDO'}

    min_marker_count: IntProperty(name="Min Marker Count", default=10)
    min_track_length: IntProperty(name="Min Track Length", default=5)
    threshold: FloatProperty(name="Detect Threshold", default=0.8, min=0.0001)

    def execute(self, context):
        logger = TrackerLogger(debug=True)
        scene = context.scene
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "No clip found")
            return {'CANCELLED'}

        motion_cycle = motion_model_cycle()

        # Step 1: Proxy Handling (simplified)
        clip.use_proxy = False
        clip.proxy.build_50 = False

        # Step 2: Detect Features with adaptive threshold
        attempts = 0
        markers_start = len(clip.tracking.tracks)
        while attempts < 10:
            bpy.ops.clip.detect_features(threshold=self.threshold)
            if len(clip.tracking.tracks) > markers_start:
                break
            self.threshold = max(0.0001, self.threshold * 0.5)
            attempts += 1
            logger.debug(f"Adjust threshold to {self.threshold}")

        # Step 3: Filter markers near GOOD_
        good_tracks = [t for t in clip.tracking.tracks if t.name.startswith('GOOD_')]
        margin = clip.size[0] / 200
        remove_nearby_tracks(clip, good_tracks, margin)
        for track in clip.tracking.tracks:
            if not track.name.startswith('TRACK_'):
                track.name = f'TRACK_{track.name}'

        # Step 4: Bidirectional tracking
        track_bidirectional(context, clip.tracking.tracks)

        # Step 5: Remove short tracks
        remove_short_tracks(clip, self.min_track_length)

        # Step 6: Re-analysis for sparse frames
        sparse_frame = find_sparse_frame(clip, self.min_marker_count)
        if sparse_frame is not None:
            clip.tracking.settings.motion_model = next(motion_cycle)
            clip.tracking.settings.default_pattern_size = min(
                clip.tracking.settings.default_pattern_size * 1.1,
                100,
            )
            set_playhead(scene, sparse_frame)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICH_OT_auto_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICH_OT_auto_track_cycle)
