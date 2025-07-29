
import bpy
import os
import shutil
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

from .prefix_good import PREFIX_GOOD
from .prefix_track import PREFIX_TRACK
from .prefix_new import PREFIX_NEW

from .feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
)

from .add_timer import add_timer
from .pattern_base import pattern_base
from .pattern_limits import pattern_limits
from .clamp_pattern_size import clamp_pattern_size
from .strip_prefix import strip_prefix
from .add_pending_tracks import add_pending_tracks
from .clean_pending_tracks import clean_pending_tracks
from .rename_pending_tracks import rename_pending_tracks
from .update_frame_display import update_frame_display
from .cycle_motion_model import cycle_motion_model
from .compute_detection_params import compute_detection_params
from .detect_new_tracks import detect_new_tracks
from .remove_close_tracks import remove_close_tracks
# Frames, die mit zu wenig Markern gefunden wurden
NF = []

# Marker count of the previous detection run
LAST_DETECT_COUNT = None

# Standard Motion Model
DEFAULT_MOTION_MODEL = 'Loc'
MOTION_MODELS = [
    'Loc',
    'LocRot',
    'LocScale',
    'LocRotScale',
    'Affine',
    'Perspective',
]

# Channel combinations for Test Detect CH
CHANNEL_COMBOS = [
    (True, False, False),
    (True, True, False),
    (True, True, True),
    (False, True, False),
    (False, True, True),
    (False, False, True),
]

# Urspr\u00fcnglicher Wert f\u00fcr "Marker/Frame"
DEFAULT_MARKER_FRAME = 20

# Minimaler Threshold-Wert f\u00fcr die Feature-Erkennung
MIN_THRESHOLD = 0.0001

# Zeitintervall für Timer-Operationen in Sekunden
TIMER_INTERVAL = 0.5

# Tracks that should be renamed after processing
PENDING_RENAME = []

# Test-Operator Ergebnisse
TEST_START_FRAME = None
TEST_END_FRAME = None
TEST_SETTINGS = {}
# Anzahl der zuletzt getrackten Frames
TRACKED_FRAMES = 0
# Letztes End-Frame-Ergebnis aus Track Full
LAST_TRACK_END = None

# Tracking attempts per frame for Track Nr. 2
TRACK_ATTEMPTS = {}

def jump_to_frame_with_few_markers(clip, min_marker_count, start_frame, end_frame):
    """Move the playhead to the first frame with too few markers.

    Iterates over ``start_frame``..``end_frame`` and sets ``scene.frame_current``
    to the first frame containing fewer than ``min_marker_count`` markers.

    Returns the found frame or ``None`` if all frames meet the requirement.
    """

    scene = bpy.context.scene
    for frame in range(start_frame, end_frame + 1):
        marker_count = sum(
            1
            for track in clip.tracking.tracks
            if any(marker.frame == frame for marker in track.markers)
        )
        if marker_count < min_marker_count:
            scene.frame_current = frame
            print(f"[JUMP] Weniger Marker ({marker_count}) in Frame {frame}")
            return frame

    print("[JUMP] Kein Frame mit zu wenig Markern gefunden.")
    return None

