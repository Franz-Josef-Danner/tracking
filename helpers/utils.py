
import bpy
import os
import shutil
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

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


def add_timer(window_manager, window):
    """Create a timer using the global `TIMER_INTERVAL`."""
    return window_manager.event_timer_add(TIMER_INTERVAL, window=window)


def pattern_base(clip):
    """Return the default pattern size based on the clip width."""
    width, _ = clip.size
    return int(width / 100)


def pattern_limits(clip):
    """Return minimum and maximum pattern size for a clip."""
    base = pattern_base(clip)
    min_size = int(base / 3)
    max_size = int(base * 3)
    return min_size, max_size


def clamp_pattern_size(value, clip):
    min_size, max_size = pattern_limits(clip)
    return max(min(value, max_size), min_size)


def strip_prefix(name):
    """Remove an existing uppercase prefix from a track name."""
    return re.sub(r'^[A-Z]+_', '', name)


def add_pending_tracks(tracks):
    """Store new tracks for later renaming with validation."""
    for t in tracks:
        try:
            if (
                isinstance(t.name, str)
                and t.name.strip()
                and t not in PENDING_RENAME
            ):
                PENDING_RENAME.append(t)
        except Exception:
            print(f"\u26a0\ufe0f Ungültiger Marker übersprungen: {t}")


def clean_pending_tracks(clip):
    """Remove deleted tracks from the pending list."""
    names = set()
    for t in clip.tracking.tracks:
        try:
            if isinstance(t.name, str) and t.name.strip():
                names.add(t.name)
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Zugriff auf Marker-Name: {t} ({e})")
    remaining = []
    for t in PENDING_RENAME:
        try:
            if t.name in names:
                remaining.append(t)
        except UnicodeDecodeError:
            print(
                f"\u26a0\ufe0f Warnung: Marker-Name kann nicht gelesen werden (wahrscheinlich defekt): {t}"
            )
            continue
    PENDING_RENAME.clear()
    PENDING_RENAME.extend(remaining)


def rename_pending_tracks(clip):
    """Rename pending tracks sequentially and clear the list."""
    clean_pending_tracks(clip)
    if not PENDING_RENAME:
        return
    existing_numbers = []
    for t in clip.tracking.tracks:
        try:
            m = re.search(r"(\d+)$", t.name)
            if m:
                existing_numbers.append(int(m.group(1)))
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Lesen des Marker-Namens: {t} ({e})")
    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    for t in PENDING_RENAME:
        try:
            _ = t.name
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Marker-Name: {t} ({e})")
            t.name = f"Track {next_num:03d}"
        else:
            t.name = f"Track {next_num:03d}"
        next_num += 1
    PENDING_RENAME.clear()


def update_frame_display(context=None):
    """Sync the Clip Editor to the scene frame and redraw."""
    if context is None:
        context = bpy.context
    space = context.space_data
    if hasattr(space, "clip_user"):
        space.clip_user.frame_current = context.scene.frame_current
    if context.area:
        context.area.tag_redraw()


def cycle_motion_model(settings, clip, reset_size=True):
    """Cycle to the next default motion model."""
    current = settings.default_motion_model
    try:
        index = MOTION_MODELS.index(current)
    except ValueError:
        index = -1
    next_model = MOTION_MODELS[(index + 1) % len(MOTION_MODELS)]
    settings.default_motion_model = next_model
    if reset_size:
        base = pattern_base(clip)
        settings.default_pattern_size = clamp_pattern_size(base, clip)
        settings.default_search_size = settings.default_pattern_size * 2


def compute_detection_params(threshold_value, margin_base, min_distance_base):
    """Return detection threshold, margin and min distance."""
    detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
    factor = math.log10(detection_threshold * 10000000000) / 10
    margin = int(margin_base * factor)
    min_distance = int(min_distance_base * factor)
    return detection_threshold, margin, min_distance


def detect_new_tracks(clip, detection_threshold, min_distance, margin):
    """Detect features and return new tracks and the state before detection."""
    names_before = {t.name for t in clip.tracking.tracks}
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()
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
    new_tracks = [t for t in clip.tracking.tracks if t.name in names_after - names_before]
    return new_tracks, names_before


def remove_close_tracks(clip, new_tracks, distance_px, names_before):
    """Delete new tracks too close to existing ones."""
    frame = bpy.context.scene.frame_current
    width, height = clip.size
    valid_positions = []
    for gt in clip.tracking.tracks:
        if (
            gt.name.startswith("GOOD_")
            or gt.name.startswith("TRACK_")
            or gt.name.startswith("NEW_")
        ):
            gm = gt.markers.find_frame(frame, exact=True)
            if gm and not gm.mute:
                valid_positions.append((gm.co[0] * width, gm.co[1] * height))

    close_tracks = []
    for nt in new_tracks:
        nm = nt.markers.find_frame(frame, exact=True)
        if nm and not nm.mute:
            nx = nm.co[0] * width
            ny = nm.co[1] * height
            for vx, vy in valid_positions:
                if math.hypot(nx - vx, ny - vy) < distance_px:
                    close_tracks.append(nt)
                    break

    for track in clip.tracking.tracks:
        track.select = False
    for t in close_tracks:
        t.select = True
    if close_tracks and bpy.ops.clip.delete_selected.poll():
        bpy.ops.clip.delete_selected()
        clean_pending_tracks(clip)

    names_after = {t.name for t in clip.tracking.tracks}
    return [t for t in clip.tracking.tracks if t.name in names_after - names_before]

